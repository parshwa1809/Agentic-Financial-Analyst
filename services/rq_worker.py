"""Simple RQ worker launcher for the project.

Run this in the `worker` container to process queued backfill jobs.
"""
import sys
import os
from rq import Worker, Queue

# Ensure project root is on sys.path so `services.*` imports work when running the script directly
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from services.redis_manager import get_redis_client

redis_conn = get_redis_client()

if __name__ == '__main__':
    # Create a default queue bound to our Redis connection and start a worker
    q = Queue(connection=redis_conn)
    worker = Worker([q], connection=redis_conn)
    worker.work()
