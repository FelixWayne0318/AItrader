"""
OCO (One-Cancels-the-Other) Order Manager with Redis Persistence

⚠️ DEPRECATED: This module is no longer used.
NautilusTrader's built-in bracket orders now handle OCO functionality automatically.
The order_factory.bracket() method creates linked SL/TP orders with native OCO support.

This file is kept for reference and backwards compatibility with documentation.
Do NOT import or use this class in new code.

Original Purpose:
Manages OCO order groups with event-driven cancellation and Redis persistence
to prevent order orphaning across strategy restarts.
"""

import json
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta

try:
    import redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False
    logging.warning("Redis not available, OCO groups will not persist across restarts")


class OCOManager:
    """
    Manages OCO (One-Cancels-the-Other) order groups.
    
    Features:
    - Event-driven automatic cancellation
    - Redis persistence for restart safety
    - Automatic cleanup of expired groups
    - In-memory fallback when Redis unavailable
    """
    
    def __init__(
        self,
        redis_host: str = "localhost",
        redis_port: int = 6379,
        redis_db: int = 0,
        redis_password: Optional[str] = None,
        key_prefix: str = "nautilus:oco",
        group_ttl_hours: int = 24,
        logger: Optional[logging.Logger] = None,
    ):
        """
        Initialize OCO Manager.
        
        Parameters
        ----------
        redis_host : str
            Redis server host
        redis_port : int
            Redis server port
        redis_db : int
            Redis database number
        redis_password : str, optional
            Redis password
        key_prefix : str
            Redis key prefix for OCO groups
        group_ttl_hours : int
            Time-to-live for OCO groups in hours
        logger : Logger, optional
            Logger instance
        """
        self.logger = logger or logging.getLogger(__name__)
        self.key_prefix = key_prefix
        self.group_ttl_seconds = group_ttl_hours * 3600
        
        # In-memory storage (always used)
        self.oco_groups: Dict[str, Dict[str, Any]] = {}
        
        # Redis connection
        self.redis_client: Optional[redis.Redis] = None
        self.redis_enabled = False
        
        if REDIS_AVAILABLE:
            try:
                self.redis_client = redis.Redis(
                    host=redis_host,
                    port=redis_port,
                    db=redis_db,
                    password=redis_password,
                    decode_responses=True,
                    socket_timeout=5,
                    socket_connect_timeout=5,
                )
                # Test connection
                self.redis_client.ping()
                self.redis_enabled = True
                self.logger.info(
                    f"✅ Redis connected: {redis_host}:{redis_port} (DB: {redis_db})"
                )
                
                # Load existing OCO groups from Redis
                self._load_from_redis()
                
            except Exception as e:
                self.logger.warning(
                    f"⚠️ Redis connection failed: {e}. Using in-memory storage only."
                )
                self.redis_client = None
                self.redis_enabled = False
        else:
            self.logger.warning("⚠️ Redis not installed. Using in-memory storage only.")
    
    def create_oco_group(
        self,
        group_id: str,
        sl_order_id: str,
        tp_order_id: str,
        instrument_id: str,
        entry_side: str,
        entry_price: float,
        quantity: float,
        sl_price: float,
        tp_price: float,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """
        Create a new OCO group.
        
        Parameters
        ----------
        group_id : str
            Unique identifier for the OCO group
        sl_order_id : str
            Stop Loss order ID
        tp_order_id : str
            Take Profit order ID
        instrument_id : str
            Trading instrument ID
        entry_side : str
            Entry side (BUY/SELL)
        entry_price : float
            Entry price
        quantity : float
            Position quantity
        sl_price : float
            Stop Loss price
        tp_price : float
            Take Profit price
        metadata : dict, optional
            Additional metadata
        
        Returns
        -------
        bool
            True if created successfully
        """
        group_data = {
            "group_id": group_id,
            "sl_order_id": sl_order_id,
            "tp_order_id": tp_order_id,
            "instrument_id": instrument_id,
            "entry_side": entry_side,
            "entry_price": entry_price,
            "quantity": quantity,
            "sl_price": sl_price,
            "tp_price": tp_price,
            "created_at": datetime.utcnow().isoformat(),
            "status": "active",
            "metadata": metadata or {},
        }
        
        # Store in memory
        self.oco_groups[group_id] = group_data
        
        # Store in Redis
        if self.redis_enabled:
            try:
                redis_key = f"{self.key_prefix}:{group_id}"
                self.redis_client.setex(
                    redis_key,
                    self.group_ttl_seconds,
                    json.dumps(group_data)
                )
                self.logger.debug(f"📝 OCO group saved to Redis: {group_id}")
            except Exception as e:
                self.logger.warning(f"⚠️ Failed to save OCO group to Redis: {e}")
        
        self.logger.info(
            f"🔗 OCO Group created [{group_id}]:\n"
            f"   Instrument: {instrument_id}\n"
            f"   Entry: {entry_side} @ ${entry_price:,.2f}\n"
            f"   SL: {sl_order_id} @ ${sl_price:,.2f}\n"
            f"   TP: {tp_order_id} @ ${tp_price:,.2f}"
        )
        
        return True
    
    def find_group_by_order(self, order_id: str) -> Optional[str]:
        """
        Find OCO group ID by order ID.
        
        Parameters
        ----------
        order_id : str
            Order ID to search for
        
        Returns
        -------
        str or None
            Group ID if found, None otherwise
        """
        for group_id, group_data in self.oco_groups.items():
            if order_id in [group_data["sl_order_id"], group_data["tp_order_id"]]:
                return group_id
        return None
    
    def get_group(self, group_id: str) -> Optional[Dict[str, Any]]:
        """
        Get OCO group data.
        
        Parameters
        ----------
        group_id : str
            Group ID
        
        Returns
        -------
        dict or None
            Group data if found
        """
        return self.oco_groups.get(group_id)
    
    def get_peer_order_id(self, group_id: str, filled_order_id: str) -> Optional[str]:
        """
        Get the peer order ID that should be cancelled.
        
        Parameters
        ----------
        group_id : str
            OCO group ID
        filled_order_id : str
            The order ID that was filled
        
        Returns
        -------
        str or None
            Peer order ID to cancel
        """
        group_data = self.oco_groups.get(group_id)
        if not group_data:
            return None
        
        sl_id = group_data["sl_order_id"]
        tp_id = group_data["tp_order_id"]
        
        if filled_order_id == sl_id:
            return tp_id
        elif filled_order_id == tp_id:
            return sl_id
        else:
            return None
    
    def mark_filled(self, group_id: str, filled_order_id: str) -> bool:
        """
        Mark an order in the OCO group as filled.
        
        Parameters
        ----------
        group_id : str
            OCO group ID
        filled_order_id : str
            Order ID that was filled
        
        Returns
        -------
        bool
            True if successful
        """
        group_data = self.oco_groups.get(group_id)
        if not group_data:
            return False
        
        # Determine which order filled
        if filled_order_id == group_data["sl_order_id"]:
            group_data["status"] = "sl_filled"
            order_type = "Stop Loss"
        elif filled_order_id == group_data["tp_order_id"]:
            group_data["status"] = "tp_filled"
            order_type = "Take Profit"
        else:
            return False
        
        group_data["filled_at"] = datetime.utcnow().isoformat()
        group_data["filled_order_id"] = filled_order_id
        
        self.logger.info(f"✅ {order_type} filled in OCO group [{group_id}]")
        
        # Update Redis
        if self.redis_enabled:
            try:
                redis_key = f"{self.key_prefix}:{group_id}"
                self.redis_client.setex(
                    redis_key,
                    3600,  # Keep for 1 hour for debugging
                    json.dumps(group_data)
                )
            except Exception as e:
                self.logger.warning(f"⚠️ Failed to update OCO group in Redis: {e}")
        
        return True
    
    def remove_group(self, group_id: str) -> bool:
        """
        Remove OCO group.
        
        Parameters
        ----------
        group_id : str
            Group ID to remove
        
        Returns
        -------
        bool
            True if removed successfully
        """
        if group_id not in self.oco_groups:
            return False
        
        # Remove from memory
        del self.oco_groups[group_id]
        
        # Remove from Redis
        if self.redis_enabled:
            try:
                redis_key = f"{self.key_prefix}:{group_id}"
                self.redis_client.delete(redis_key)
                self.logger.debug(f"🗑️ OCO group removed from Redis: {group_id}")
            except Exception as e:
                self.logger.warning(f"⚠️ Failed to remove OCO group from Redis: {e}")
        
        self.logger.info(f"🗑️ OCO Group [{group_id}] removed")
        return True
    
    def cleanup_expired_groups(self) -> int:
        """
        Clean up expired OCO groups (older than TTL).
        
        Returns
        -------
        int
            Number of groups cleaned up
        """
        now = datetime.utcnow()
        expired_groups = []
        
        for group_id, group_data in self.oco_groups.items():
            created_at = datetime.fromisoformat(group_data["created_at"])
            age_seconds = (now - created_at).total_seconds()
            
            if age_seconds > self.group_ttl_seconds:
                expired_groups.append(group_id)
                self.logger.warning(
                    f"⚠️ OCO group [{group_id}] expired (age: {age_seconds/3600:.1f}h)"
                )
        
        # Remove expired groups
        for group_id in expired_groups:
            self.remove_group(group_id)
        
        if expired_groups:
            self.logger.info(f"🗑️ Cleaned up {len(expired_groups)} expired OCO groups")
        
        return len(expired_groups)
    
    def get_all_groups(self) -> Dict[str, Dict[str, Any]]:
        """
        Get all OCO groups.
        
        Returns
        -------
        dict
            All OCO groups
        """
        return self.oco_groups.copy()
    
    def get_active_count(self) -> int:
        """
        Get count of active OCO groups.
        
        Returns
        -------
        int
            Number of active groups
        """
        return len([g for g in self.oco_groups.values() if g["status"] == "active"])
    
    def _load_from_redis(self):
        """Load existing OCO groups from Redis on startup."""
        if not self.redis_enabled:
            return
        
        try:
            pattern = f"{self.key_prefix}:*"
            keys = self.redis_client.keys(pattern)
            
            loaded_count = 0
            for key in keys:
                try:
                    data = self.redis_client.get(key)
                    if data:
                        group_data = json.loads(data)
                        group_id = group_data["group_id"]
                        self.oco_groups[group_id] = group_data
                        loaded_count += 1
                except Exception as e:
                    self.logger.warning(f"⚠️ Failed to load OCO group from {key}: {e}")
            
            if loaded_count > 0:
                self.logger.info(f"📥 Loaded {loaded_count} OCO groups from Redis")
        
        except Exception as e:
            self.logger.error(f"❌ Failed to load OCO groups from Redis: {e}")
    
    def get_statistics(self) -> Dict[str, Any]:
        """
        Get OCO manager statistics.
        
        Returns
        -------
        dict
            Statistics
        """
        stats = {
            "total_groups": len(self.oco_groups),
            "active_groups": self.get_active_count(),
            "redis_enabled": self.redis_enabled,
            "groups_by_status": {},
        }
        
        for group_data in self.oco_groups.values():
            status = group_data["status"]
            stats["groups_by_status"][status] = stats["groups_by_status"].get(status, 0) + 1
        
        return stats
    
    def __repr__(self):
        stats = self.get_statistics()
        return (
            f"OCOManager(total={stats['total_groups']}, "
            f"active={stats['active_groups']}, "
            f"redis={stats['redis_enabled']})"
        )

