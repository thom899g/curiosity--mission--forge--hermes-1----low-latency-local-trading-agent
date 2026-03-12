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