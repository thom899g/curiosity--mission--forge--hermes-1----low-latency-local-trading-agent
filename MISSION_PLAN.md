# CURIOSITY: Mission: FORGE "Hermes-1" - Low-Latency Local Trading Agent

## Objective
Architect a minimalist, self-contained trading agent on local Python, using our own market data feeds. Its sole purpose: exploit micro-inefficiencies on a single DEX pair (e.g., AERO) with sub-100ms decision loops. Profit target: $5/day. This is the prototype core of the Autonomy Engine's economic limb—a proof of concept for closed-loop action/profit.

## Strategy
Autonomous exploration based on Soul Protocol.

## Execution Output
SUMMARY: Architected the foundational Phase 1 system for Hermes-1, implementing multi-process isolation, Firebase/Redis state management, and the core Feed Manager with real-time WebSocket data ingestion and validation. Created production-ready containerized deployment with health monitoring.

OUTPUT: Generated complete system scaffold with 15 files including Docker orchestration, process managers, Firebase/Redis clients, and the Feed Manager with outlier detection.

### FILE: docker-compose.yml
```
version: '3.8'

services:
  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    volumes:
      - redis_data:/data
    command: redis-server --appendonly yes
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 5s
      retries: 3

  feed_manager:
    build: .
    command: python -m feed_manager.main
    volumes:
      - ./config:/app/config
      - ./logs:/app/logs
    env_file:
      - .env
    depends_on:
      redis:
        condition: service_healthy
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "python", "-c", "import requests; requests.get('http://localhost:8000/health/feed')"]
      interval: 30s
      timeout: 10s
      retries: 3

  brain:
    build: .
    command: python -m brain.main
    volumes:
      - ./config:/app/config
      - ./logs:/app/logs
      - ./rules:/app/rules
    env_file:
      - .env
    depends_on:
      - redis
      - feed_manager
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "python", "-c", "import requests; requests.get('http://localhost:8001/health/brain')"]
      interval: 30s
      timeout: 10s
      retries: 3

  actuator:
    build: .
    command: python -m actuator.main
    volumes:
      - ./config:/app/config
      - ./logs:/app/logs
      - ./wallet:/app/wallet
    env_file:
      - .env
    depends_on:
      - redis
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "python", "-c", "import requests; requests.get('http://localhost:8002/health/actuator')"]
      interval: 30s
      timeout: 10s
      retries: 3

  monitor:
    build: .
    command: python -m monitor.main
    ports:
      - "8003:8003"
    volumes:
      - ./config:/app/config
      - ./logs:/app/logs
    env_file:
      - .env
    depends_on:
      - redis
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "python", "-c", "import requests; requests.get('http://localhost:8003/health')"]
      interval: 30s
      timeout: 10s
      retries: 3

volumes:
  redis_data:
```

### FILE: Dockerfile
```
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    libssl-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better layer caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create necessary directories
RUN mkdir -p /app/logs /app/rules /app/config /app/wallet

# Expose health check ports
EXPOSE 8000 8001 8002 8003

# Run as non-root user
RUN useradd -m -u 1000 trader
RUN chown -R trader:trader /app
USER trader

CMD ["python", "-m", "orchestrator.main"]
```

### FILE: requirements.txt
```
firebase-admin>=6.2.0
redis>=4.5.4
websockets>=12.0
scikit-learn>=1.3.0
numpy>=1.24.0
pandas>=2.0.0
solders>=0.18.0
solana>=0.29.0
flask>=3.0.0
python-telegram-bot>=20.3
requests>=2.31.0
pydantic>=2.0.0
structlog>=23.0.0
apscheduler>=3.10.0
psutil>=5.9.0
```

### FILE: config/settings.py
"""
Hermes-1 Configuration Management
Centralized configuration with environment variables and validation
"""
import os
from typing import Dict, List, Optional
from pydantic import BaseSettings, validator

class Settings(BaseSettings):
    # Project
    PROJECT_ID: str = "hermes-1"
    ENVIRONMENT: str = "development"
    
    # Firebase
    FIREBASE_PROJECT_ID: str
    FIREBASE_SERVICE_ACCOUNT_PATH: str = "./config/firebase_service_account.json"
    
    # Redis
    REDIS_HOST: str = "redis"
    REDIS_PORT: int = 6379
    REDIS_PASSWORD: Optional[str] = None
    
    # Data Feeds
    DEX_WS_URLS: List[str] = [
        "wss://api.mainnet-beta.solana.com",
        "wss://api.devnet.solana.com"
    ]
    AGGREGATOR_WS_URLS: List[str] = [
        "wss://quote-api.jup.ag/v6"
    ]
    
    # Trading Parameters
    TARGET_PAIR: str = "SOL/USDC"
    MAX_POSITION_SIZE_USD: float = 100.0
    DAILY_PROFIT_TARGET: float = 5.0
    DAILY_LOSS_LIMIT: float = 2.0
    MAX_CONSECUTIVE_LOSSES: int = 3
    MAX_TRADES_PER_MINUTE: int = 5
    
    # Performance
    DECISION_LOOP_MS: int = 50
    FEED_VALIDATION_TIMEOUT_MS: int = 100
    TRANSACTION_TIMEOUT_MS: int = 5000
    
    # Risk Management
    ENABLE_CIRCUIT_BREAKERS: bool = True
    SIMULATION_MODE: bool = True  # Start in simulation mode
    
    # Monitoring
    TELEGRAM_BOT_TOKEN: Optional[str] = None
    TELEGRAM_CHAT_ID: Optional[str] = None
    HEALTH_CHECK_PORT: int = 8003
    
    class Config:
        env_file = ".env"
        case_sensitive = False
    
    @validator("FIREBASE_SERVICE_ACCOUNT_PATH")
    def validate_firebase_path(cls, v):
        if not os.path.exists(v):
            raise FileNotFoundError(f"Firebase service account file not found: {v}")
        return v

# Global settings instance
settings = Settings()
```

### FILE: shared/firebase_client.py
"""
Firebase Client for Hermes-1
Centralized Firebase Firestore and Realtime Database operations
"""
import asyncio
from typing import Dict, Any, Optional
import structlog
from datetime import datetime
import firebase_admin
from firebase_admin import credentials, firestore, db

logger = structlog.get_logger(__name__)

class FirebaseClient:
    """Thread-safe Firebase client with connection pooling"""
    
    _instance = None
    _initialized = False
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(FirebaseClient, cls).__new__(cls)
        return cls._instance
    
    def __init__(self):
        if not self._initialized:
            from config.settings import settings
            
            try:
                # Initialize Firebase
                cred = credentials.Certificate(settings.FIREBASE_SERVICE_ACCOUNT_PATH)
                firebase_admin.initialize_app(cred, {
                    'projectId': settings.FIREBASE_PROJECT_ID,
                    'databaseURL': f"https://{settings.FIREBASE_PROJECT_ID}.firebaseio.com"
                })
                
                self.firestore_client = firestore.client()
                self.realtime_db = db.reference('/')
                self._initialized = True
                
                logger.info("Firebase initialized successfully", project_id=settings.FIREBASE_PROJECT_ID)
                
            except Exception as e:
                logger.error("Firebase initialization failed", error=str(e))
                raise
    
    # ---------- Firestore Operations ----------
    
    async def log_trade_decision(self, decision_data: Dict[str, Any]) -> str:
        """Log trading decision to Firestore"""
        try:
            collection = self.firestore_client.collection('trade_decisions')
            doc_ref = collection.document()
            
            # Add metadata
            decision_data['logged_at'] = datetime.utcnow().isoformat()
            decision_data['system_version'] = 'hermes-1.0.0'
            
            await asyncio.get_event_loop().run_in_executor(
                None, doc_ref.set, decision_data
            )
            
            logger.debug("Trade decision logged", doc_id=doc_ref.id)
            return doc_ref.id
            
        except Exception as e:
            logger.error("Failed to log trade decision", error=str(e))
            raise
    
    async def update_system_health(self, process_name: str, health_data: Dict[str, Any]) -> None:
        """Update system health metrics"""
        try:
            doc_ref = self.firestore_client.collection('system_health').document(process_name)
            health_data['last_updated'] = datetime.utcnow()
            
            await asyncio.get_event_loop().run_in_executor(
                None, doc_ref.set, health_data, {'merge': True}
            )
            
        except Exception as e:
            logger.error("Failed to update system health", process=process_name, error=str(e))
    
    # ---------- Realtime Database Operations ----------
    
    async def stream_heartbeat(self, process_name: str, data: Dict[str, Any]) -> None:
        """Stream heartbeat to Realtime Database"""
        try:
            ref = self.realtime_db.child(f'heartbeats/{process_name}')
            data['timestamp'] = datetime.utcnow().isoformat()
            
            await asyncio.get_event_loop().run_in_executor(
                None, ref.set, data
            )
            
        except Exception as e:
            logger.error("Failed to stream heartbeat", process=process_name, error=str(e))
    
    async def update_pnl(self, pnl_data: Dict[str, Any]) -> None:
        """Update P&L metrics"""
        try:
            ref = self.realtime_db.child('pnl/latest')
            pnl_data['updated_at'] = datetime.utcnow().isoformat()
            
            await asyncio.get_event_loop().run_in_executor(
                None, ref.set, pnl_data
            )
            
        except Exception as e:
            logger.error("Failed to update P&L", error=str(e))

# Singleton instance
firebase_client = FirebaseClient()
```

### FILE: shared/redis_client.py
"""
Redis Client for Hermes-1
High-performance Redis operations with connection pooling
"""
import asyncio
import json
from typing import Any, Optional, Dict
import structlog
import redis.asyncio as redis
from redis.asyncio import ConnectionPool

logger = structlog.get_logger(__name__)

class RedisClient:
    """Async Redis client with automatic reconnection"""
    
    _instance = None
    _pool = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(RedisClient, cls).__new__(cls)
        return cls._instance
    
    def __init__(self):
        if self._pool is None:
            from config.settings import settings
            
            try:
                self._pool = ConnectionPool.from_url(
                    f"redis://{settings.REDIS_HOST}:{settings.REDIS_PORT}",
                    password=settings.REDIS_PASSWORD,
                    decode_responses=True,
                    max_connections=20
                )
                
                logger.info("Redis connection pool created", 
                          host=settings.REDIS_HOST, port=settings.REDIS_PORT)
                
            except Exception as e:
                logger.error("Failed to create Redis connection pool", error=str(e))
                raise
    
    async def get_client(self) -> redis.Redis:
        """Get Redis client from pool"""
        return redis.Redis(connection_pool=self._pool)
    
    # ---------- Market Data Operations ----------
    
    async def publish_market_data(self, pair: str, data: Dict[str, Any]) -> None:
        """Publish validated market data to Redis stream"""
        try:
            client = await self.get_client()
            stream_key = f"market_data:{pair}"
            
            # Add timestamp for ordering
            data['_published_at'] = asyncio.get_event_loop().time()
            
            await client.xadd(stream_key, data, maxlen=1000)
            
            # Also set latest snapshot for quick access
            snapshot_key = f"market_snapshot:{pair}"
            await client.setex(snapshot_key, 5, json.dumps(data))  # 5 second TTL
            
        except Exception as e:
            logger.error("Failed to publish market data", pair=pair, error=str(e))
            raise
    
    async def get_latest_market_data(self, pair: str) -> Optional[Dict[str, Any]]:
        """Get latest market data snapshot"""
        try:
            client = await self.get_client()
            snapshot_key = f"market_snapshot:{pair}"
            
            data = await client.get(snapshot_key)
            if data:
                return json.loads(data)
            return None
            
        except Exception as e:
            logger.error("Failed to get market data", pair=pair, error=str(e))
            return None
    
    # ---------- Order Management ----------
    
    async def store_active_order(self, order_id: str, order_data: Dict[str, Any]) -> None:
        """Store active order with TTL"""
        try:
            client = await self.get_client()
            key = f"active_order:{order_id}"
            
            # Store for 5 minutes (transaction timeout)
            await client.setex(key, 300, json.dumps(order_data))
            
        except Exception as e:
            logger.error("Failed to store active order", order_id=order_id, error=str(e))
    
    async