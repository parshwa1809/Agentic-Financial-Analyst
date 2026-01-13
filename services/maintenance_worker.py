import sys
import os
import time
import pandas as pd
from datetime import datetime, timedelta

# Ensure project root is on sys.path
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from services.db_manager import get_engine, execute_query
from services.redis_manager import get_redis_client
from rq import Queue

# Import Tasks
from services.seed_supply_chain import discover_partners
# Import backfill task lazily to avoid circular imports if needed

engine = get_engine()
redis_conn = get_redis_client()
queue = Queue(connection=redis_conn)

def prune_old_data():
    """Deletes data older than 90 days to save space."""
    print("🧹 Maintenance: Pruning old data...")
    try:
        execute_query("DELETE FROM market_data WHERE timestamp < NOW() - INTERVAL 90 DAY")
        execute_query("DELETE FROM news_articles WHERE published_at < NOW() - INTERVAL 90 DAY")
        print("✅ Pruning complete.")
    except Exception as e:
        print(f"❌ Pruning Error: {e}")

def check_missing_supply_chain():
    """
    Checks for Active Tickers that have NO supply chain data and queues them.
    """
    print("🕵️ Maintenance: Checking for missing supply chain data...")
    try:
        # Find active tickers that are NOT in the supply_chain table
        query = """
            SELECT t.symbol 
            FROM tickers t 
            LEFT JOIN supply_chain s ON t.symbol = s.ticker 
            WHERE t.is_active = 1 
            AND s.id IS NULL
        """
        df = pd.read_sql(query, engine)
        
        if not df.empty:
            missing_tickers = df['symbol'].tolist()
            print(f"   ⚠️ Found {len(missing_tickers)} tickers with no supply chain data. Queueing...")
            
            for ticker in missing_tickers:
                queue.enqueue(discover_partners, ticker, job_timeout='2m')
                print(f"      -> Queued {ticker}")
        else:
            print("   ✅ All active tickers have supply chain data.")
            
    except Exception as e:
        print(f"❌ Supply Chain Check Error: {e}")

def check_for_stale_tickers():
    """Checks if any ACTIVE ticker has not updated in the last 60 minutes."""
    print("🕵️ Maintenance: Checking for stale price data...")
    # ... (Keep your existing backfill logic here if you want) ...
    # For brevity, ensuring the Supply Chain logic is the focus.

if __name__ == "__main__":
    print("🛡️ Maintenance Worker Started (Pruner + Watchdog)...")
    
    while True:
        # 1. Check for missing supply chain data (Every 5 mins)
        check_missing_supply_chain()
        
        # 2. Prune old data (Once per hour)
        if datetime.now().minute == 0: 
            prune_old_data()
            
        time.sleep(300) # Sleep 5 minutes