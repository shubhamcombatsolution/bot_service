# engine/cache_service_hybrid.py
import json
import hashlib
import redis
from sqlalchemy import text
from typing import Dict, Any, Optional
import inspect
from engine.registry import NODE_REGISTRY
import logging

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

class HybridCacheService:
    """Redis + SQLAlchemy hybrid caching and checkpoint system."""

    def __init__(self, redis_url: str, db_session, redis_ttl: int = 86400, debug: bool = False):
        self.redis = redis.StrictRedis.from_url(redis_url, decode_responses=True)
        self.redis_ttl = redis_ttl
        self.db_session = db_session
        self.debug = debug

    # ---------- Utility ----------
    def compute_cache_key(self, node_def: Dict[str, Any], inputs: Dict[str, Any]) -> str:
        node_id = node_def["id"]
        node_type = node_def.get("type")
        NodeClass = NODE_REGISTRY.get(node_type)
        node_code_hash = hashlib.sha256(inspect.getsource(NodeClass).encode()).hexdigest() if NodeClass else "unknown"
        
        # Prepare payload components
        node_data = node_def.get("data", {})
        
        # 🔍 LOG: Show what's going into the cache key
        if self.debug:
            logger.info(f"━━━ Computing Cache Key for {node_type} ({node_id[:8]}...) ━━━")
            logger.info(f"  Node Data: {json.dumps(node_data, default=str)[:200]}...")
            logger.info(f"  Input Keys: {list(inputs.keys())}")
            
            # Show actual input data (truncated for readability)
            for input_key, input_value in inputs.items():
                if isinstance(input_value, dict):
                    logger.info(f"  Input[{input_key}]: {json.dumps(input_value, default=str)[:200]}...")
                elif isinstance(input_value, list):
                    logger.info(f"  Input[{input_key}]: List with {len(input_value)} items")
                else:
                    logger.info(f"  Input[{input_key}]: {str(input_value)[:100]}...")
        
        # Build payload
        payload = {
            "node_id": node_id,
            "type": node_type,
            "code_hash": node_code_hash,
            "data": node_data,
            "inputs": inputs
        }
        
        payload_str = json.dumps(payload, sort_keys=True, default=str)
        cache_key = hashlib.sha256(payload_str.encode()).hexdigest()
        
        # 🔍 LOG: Show the final cache key and payload hash
        if self.debug:
            payload_hash = hashlib.sha256(json.dumps(inputs, sort_keys=True, default=str).encode()).hexdigest()
            logger.info(f"  Inputs Hash: {payload_hash[:16]}...")
            logger.info(f"  Final Cache Key: {cache_key[:16]}...")
            logger.info(f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        
        return cache_key

    # ---------- Node Cache ----------
    def get_cached_output(self, cache_key: str) -> Optional[Dict[str, Any]]:
        data = self.redis.get(cache_key)
        if self.debug:
            if data:
                logger.info(f"✅ Cache HIT for key: {cache_key[:16]}...")
                # Show what's being returned
                cached_data = json.loads(data)
                if isinstance(cached_data, dict):
                    logger.info(f"   Returning cached data with keys: {list(cached_data.keys())}")
                else:
                    logger.info(f"   Returning cached data: {str(cached_data)[:100]}...")
            else:
                logger.info(f"❌ Cache MISS for key: {cache_key[:16]}...")
        return json.loads(data) if data else None

    def set_cached_output(self, cache_key: str, output: Dict[str, Any], ttl_override: int = None):
        ttl = ttl_override or self.redis_ttl
        
        # 🔍 LOG: Show what's being cached
        if self.debug:
            logger.info(f"💾 Caching output for key: {cache_key[:16]}... (TTL={ttl}s)")
            if isinstance(output, dict):
                logger.info(f"   Caching data with keys: {list(output.keys())}")
                logger.info(f"   Data preview: {json.dumps(output, default=str)[:200]}...")
            else:
                logger.info(f"   Caching data: {str(output)[:100]}...")
        
        self.redis.setex(cache_key, ttl, json.dumps(output, default=str))

    # ---------- Checkpoints ----------
    def save_checkpoint(self, workflow_id: str, execution_id: str, context: Dict[str, Any]):
        query = text("""
            INSERT INTO workflow_checkpoints (workflow_id, execution_id, context, created_at, updated_at)
            VALUES (:workflow_id, :execution_id, CAST(:context AS JSONB), NOW(), NOW())
            ON CONFLICT (execution_id)
            DO UPDATE SET context = EXCLUDED.context, updated_at = NOW();
        """)
        self.db_session.execute(query, {
            "workflow_id": workflow_id,
            "execution_id": execution_id,
            "context": json.dumps(context)
        })
        self.db_session.commit()
        if self.debug:
            logger.info(f"Checkpoint saved for workflow {workflow_id} / execution {execution_id}")

    def load_checkpoint(self, workflow_id: str, execution_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        if execution_id:
            query = text("""
                SELECT context FROM workflow_checkpoints
                WHERE workflow_id = :workflow_id AND execution_id = :execution_id
                LIMIT 1;
            """)
            params = {"workflow_id": workflow_id, "execution_id": execution_id}
        else:
            query = text("""
                SELECT context FROM workflow_checkpoints
                WHERE workflow_id = :workflow_id
                ORDER BY updated_at DESC LIMIT 1;
            """)
            params = {"workflow_id": workflow_id}

        result = self.db_session.execute(query, params).fetchone()
        if self.debug:
            if result:
                logger.info(f"Checkpoint loaded for workflow {workflow_id} / execution {execution_id or 'latest'}")
            else:
                logger.info(f"No checkpoint found for workflow {workflow_id} / execution {execution_id or 'latest'}")
        return result[0] if result else None

        
# class HybridCacheService:
#     """Redis + SQLAlchemy hybrid caching and checkpoint system."""

#     def __init__(self, redis_url: str, db_session, redis_ttl: int = 86400, debug: bool = False):
#         self.redis = redis.StrictRedis.from_url(redis_url, decode_responses=True)
#         self.redis_ttl = redis_ttl
#         self.db_session = db_session
#         self.debug = debug

#     # ---------- Utility ----------
#     def compute_cache_key(self, node_def: Dict[str, Any], inputs: Dict[str, Any]) -> str:
#         node_type = node_def.get("type")
#         NodeClass = NODE_REGISTRY.get(node_type)
#         node_code_hash = hashlib.sha256(inspect.getsource(NodeClass).encode()).hexdigest() if NodeClass else "unknown"
        
#         payload = json.dumps({
#             "node_id": node_def["id"],
#             "type": node_type,
#             "code_hash": node_code_hash,
#             "data": node_def.get("data", {}),
#             "inputs": inputs
#         }, sort_keys=True, default=str)
#         return hashlib.sha256(payload.encode()).hexdigest()

#     # ---------- Node Cache ----------
#     def get_cached_output(self, cache_key: str) -> Optional[Dict[str, Any]]:
#         data = self.redis.get(cache_key)
#         if self.debug:
#             if data:
#                 logger.info(f"Cache HIT for key: {cache_key}")
#             else:
#                 logger.info(f"Cache MISS for key: {cache_key}")
#         return json.loads(data) if data else None

#     def set_cached_output(self, cache_key: str, output: Dict[str, Any], ttl_override: int = None):
#         ttl = ttl_override or self.redis_ttl
#         self.redis.setex(cache_key, ttl, json.dumps(output))
#         if self.debug:
#             logger.info(f"Cached output for key: {cache_key} (TTL={ttl}s)")


#     # ---------- Checkpoints ----------
#     def save_checkpoint(self, workflow_id: str, execution_id: str, context: Dict[str, Any]):
#         query = text("""
#             INSERT INTO workflow_checkpoints (workflow_id, execution_id, context, created_at, updated_at)
#             VALUES (:workflow_id, :execution_id, CAST(:context AS JSONB), NOW(), NOW())
#             ON CONFLICT (execution_id)
#             DO UPDATE SET context = EXCLUDED.context, updated_at = NOW();
#         """)
#         self.db_session.execute(query, {
#             "workflow_id": workflow_id,
#             "execution_id": execution_id,
#             "context": json.dumps(context)
#         })
#         self.db_session.commit()
#         if self.debug:
#             logger.info(f"Checkpoint saved for workflow {workflow_id} / execution {execution_id}")

#     def load_checkpoint(self, workflow_id: str, execution_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
#         if execution_id:
#             query = text("""
#                 SELECT context FROM workflow_checkpoints
#                 WHERE workflow_id = :workflow_id AND execution_id = :execution_id
#                 LIMIT 1;
#             """)
#             params = {"workflow_id": workflow_id, "execution_id": execution_id}
#         else:
#             query = text("""
#                 SELECT context FROM workflow_checkpoints
#                 WHERE workflow_id = :workflow_id
#                 ORDER BY updated_at DESC LIMIT 1;
#             """)
#             params = {"workflow_id": workflow_id}

#         result = self.db_session.execute(query, params).fetchone()
#         if self.debug:
#             if result:
#                 logger.info(f"Checkpoint loaded for workflow {workflow_id} / execution {execution_id or 'latest'}")
#             else:
#                 logger.info(f"No checkpoint found for workflow {workflow_id} / execution {execution_id or 'latest'}")
#         return result[0] if result else None
