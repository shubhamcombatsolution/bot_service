import json
import hashlib
from uuid import UUID
from datetime import datetime

def make_json_safe(obj):
    if isinstance(obj, dict):
        return {k: make_json_safe(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [make_json_safe(i) for i in obj]
    elif isinstance(obj, UUID):
        return str(obj)
    elif isinstance(obj, datetime):
        return obj.isoformat()
    else:
        return obj

def compute_snapshot_hash(snapshot: dict) -> str:
    normalized = json.dumps(snapshot, sort_keys=True, default=make_json_safe)
    return hashlib.sha256(normalized.encode()).hexdigest()

