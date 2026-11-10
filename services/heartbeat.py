"""
Worker heartbeats, so the UI shows each background agent's real state instead
of a hard-coded green dot.

Each worker calls beat("<name>", "ok" | "error" | "idle", "short detail").
The API reads them back in /api/system/status.
"""
import json
import time

from services.redis_manager import get_redis_client

_r = get_redis_client()


def beat(name: str, status: str = "ok", detail: str = "", ttl: int = 7200) -> None:
    try:
        _r.set(f"heartbeat:{name}", json.dumps({"status": status, "detail": detail[:200], "ts": time.time()}), ex=ttl)
    except Exception:
        pass  # a heartbeat must never break the worker


def read(name: str):
    try:
        raw = _r.get(f"heartbeat:{name}")
        return json.loads(raw) if raw else None
    except Exception:
        return None
