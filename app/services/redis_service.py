# app/services/redis_service.py

import json
import redis
from flask import current_app


class RedisService:

    def _get_client(self):
        return redis.Redis(
            host=current_app.config.get("REDIS_HOST", "redis"),  # 👈 IMPORTANT
            port=current_app.config.get("REDIS_PORT", 6379),
            db=current_app.config.get("REDIS_DB", 0),
            decode_responses=True
        )

    # ─────────────────────────────
    # Basic Operations
    # ─────────────────────────────

    def get(self, key):
        client = self._get_client()
        value = client.get(key)
        return json.loads(value) if value else None

    def set(self, key, value, ttl=None):
        client = self._get_client()
        serialized = json.dumps(value)
        if ttl:
            client.setex(key, ttl, serialized)
        else:
            client.set(key, serialized)

    def delete(self, key):
        client = self._get_client()
        client.delete(key)

    def exists(self, key):
        client = self._get_client()
        return client.exists(key)

    def delete_pattern(self, pattern):
        client = self._get_client()
        for key in client.scan_iter(pattern):
            client.delete(key)
            
    
    def push_to_queue(self, queue_name, payload):
        client = self._get_client()
        client.rpush(queue_name, json.dumps(payload))

    def pop_from_queue(self, queue_name):
        client = self._get_client()
        _, data = client.blpop(queue_name)
        return json.loads(data)