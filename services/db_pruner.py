import sys
import os
# Ensure project root is on sys.path
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import time
from services.db_manager import execute_query

def prune():
    print("🧹 Pruning Old Data...")
    try:
        execute_query("DELETE FROM market_data WHERE timestamp < NOW() - INTERVAL 90 DAY")
        execute_query("DELETE FROM news_articles WHERE published_at < NOW() - INTERVAL 90 DAY")
        print("✅ Pruning complete.")
    except Exception as e:
        print(f"❌ Pruner Error: {e}")

if __name__ == "__main__":
    while True:
        prune()
        time.sleep(86400)