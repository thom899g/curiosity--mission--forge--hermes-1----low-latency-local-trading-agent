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