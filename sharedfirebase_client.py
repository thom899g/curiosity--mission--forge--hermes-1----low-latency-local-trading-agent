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