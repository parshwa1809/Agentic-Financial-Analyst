import redis
import os

# RQ and the redis client expect raw bytes for some registry entries and job data.
# Do NOT enable `decode_responses` globally; leave responses as bytes so RQ can
# manage decoding/encoding itself. Callers that need strings should decode
# explicitly where appropriate.
r = redis.Redis(host=os.getenv('REDIS_HOST', 'redis-queue'), port=int(os.getenv('REDIS_PORT', 6379)), db=0, decode_responses=False)

def get_redis_client():
    return r