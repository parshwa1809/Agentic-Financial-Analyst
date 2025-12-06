import sys
import os
# Ensure project root is on sys.path
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import time
import json
import asyncio
from alpaca_trade_api.stream import Stream
from services.redis_manager import get_redis_client
from services.db_manager import get_engine
import pandas as pd
import os

ALPACA_KEY = os.getenv("ALPACA_KEY")
ALPACA_SECRET = os.getenv("ALPACA_SECRET")

# Connect to Redis & DB
redis_client = get_redis_client()
engine = get_engine()

def get_active_tickers():
    try:
        df = pd.read_sql("SELECT symbol FROM tickers WHERE is_active = 1", engine)
        return df['symbol'].tolist()
    except: return []

async def bar_handler(bar):
    """Handles Stock Bars (1-Min)"""
    try:
        data = {
            "ticker": bar.S,
            "timestamp": str(bar.t),
            "price": float(bar.c),
            "size": int(bar.v),
            "open": float(bar.o),
            "high": float(bar.h),
            "low": float(bar.l),
            "close": float(bar.c),
            "volume": int(bar.v)
        }
        json_data = json.dumps(data)
        
        # 1. Push to DB Writer
        redis_client.rpush("trade_queue", json_data)
        
        # 2. Push to Alert Engine (Sliding Window)
        redis_client.zadd(f"window:{bar.S}", {json_data: time.time()})
        redis_client.zremrangebyrank(f"window:{bar.S}", 0, -101)
    except Exception as e:
        print(f"Handler Error: {e}")

def run_stream():
    while True:
        tickers = get_active_tickers()
        if tickers:
            print(f"🔌 Starting Stock Stream for: {tickers}")
            try:
                # STOCKS ONLY (IEX Feed)
                stream = Stream(
                    ALPACA_KEY, 
                    ALPACA_SECRET, 
                    base_url="https://paper-api.alpaca.markets", 
                    data_feed='iex' 
                )
                stream.subscribe_bars(bar_handler, *tickers)
                stream.run()
            except Exception as e:
                print(f"Stream Error: {e}. Restarting in 5s...")
                time.sleep(5)
        else:
            print("💤 No active tickers. Waiting 10s...")
            time.sleep(10)

if __name__ == "__main__":
    time.sleep(10)
    run_stream()