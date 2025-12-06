import uuid
from services.redis_manager import get_redis_client

_DEL_SCRIPT = """
if redis.call('get', KEYS[1]) == ARGV[1] then
    return redis.call('del', KEYS[1])
else
    return 0
end
"""

def acquire_lock(key: str, ttl: int = 3600):
    """Try to acquire a lock named `key` with TTL seconds.

    Returns a token string if lock acquired, otherwise None.
    """
    r = get_redis_client()
    token = str(uuid.uuid4())
    acquired = r.set(key, token, nx=True, ex=ttl)
    if acquired:
        return token
    return None

def release_lock(key: str, token: str):
    """Release lock only if token matches. Uses Lua script for atomicity."""
    r = get_redis_client()
    try:
        return r.eval(_DEL_SCRIPT, 1, key, token)
    except Exception:
        # Fallback: attempt a simple delete (not safe if token mismatch)
        try:
            cur = r.get(key)
            # When decode_responses=False the client returns bytes; decode to str for comparison.
            if isinstance(cur, (bytes, bytearray)):
                try:
                    cur_decoded = cur.decode('utf-8')
                except Exception:
                    cur_decoded = cur.decode('utf-8', errors='ignore')
            else:
                cur_decoded = cur

            if cur_decoded == token:
                return r.delete(key)
        except Exception:
            return 0
    return 0
