import sys
import os
# Ensure project root is on sys.path
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import time
import json
import pandas as pd
from services.redis_manager import get_redis_client
from services.db_manager import get_engine

r = get_redis_client()
engine = get_engine()
BATCH_SIZE = 50

def process_queue():
    print("💾 DB Writer Active...")
    while True:
        batch = []
        # Use blpop for better efficiency if the queue is empty
        item_tuple = r.blpop("trade_queue", timeout=5)
        if item_tuple:
            # item_tuple is (queue_name, data), data is bytes
            batch.append(json.loads(item_tuple[1].decode('utf-8')))
            # Try to grab more non-blocking items to fill the batch
            for _ in range(BATCH_SIZE - 1):
                item = r.lpop("trade_queue")
                if item: 
                    batch.append(json.loads(item.decode('utf-8')))
                else: 
                    break

        if not batch:
            continue
            
        try:
            df = pd.DataFrame(batch)
            # Ensure columns match schema
            df_sql = pd.DataFrame()
            df_sql['ticker'] = df['ticker']
            df_sql['timestamp'] = pd.to_datetime(df['timestamp'])
            df_sql['close'] = df['close']
            df_sql['volume'] = df['volume']
            df_sql['open'] = df['open']
            df_sql['high'] = df['high']
            df_sql['low'] = df['low']
            
            df_sql.to_sql('market_data', engine, if_exists='append', index=False)
            print(f"✅ Saved {len(df)} bars")
        except Exception as e:
            print(f"❌ Write Error: {e}")
            # Note: Data loss possible here if we don't rpush, but this ensures loop doesn't stall
            
if __name__ == "__main__":
    time.sleep(15)
    process_queue()