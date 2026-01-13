import time
import sys
import os
from sqlalchemy import text

# Add the project root to the path to ensure imports resolve correctly
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import core logic and database management
from services.db_manager import get_engine, execute_query
from app.internal.agent_council import run_council

engine = get_engine()

def get_active_tickers():
    """Fetches symbols for all tickers currently marked as active in the DB."""
    try:
        with engine.connect() as conn:
            rows = conn.execute(text("SELECT symbol FROM tickers WHERE is_active=1")).fetchall()
        return [r[0] for r in rows]
    except Exception as e:
        print(f"⚠️ DB Error: {e}")
        return []

def needs_update(ticker):
    """Checks if a verdict exists that is less than 1 hour old."""
    try:
        with engine.connect() as conn:
            query = text("""
                SELECT created_at FROM council_verdicts 
                WHERE ticker = :t 
                AND created_at >= datetime('now', '-1 hour') 
                ORDER BY created_at DESC LIMIT 1
            """)
            row = conn.execute(query, {"t": ticker}).fetchone()
            
        if row:
            print(f"   ✅ {ticker} is fresh (analyzed at {row[0]}). Skipping.")
            return False 
        return True 
    except:
        return True

def run_continuous_council():
    """Main loop for the autonomous Council Agent."""
    print("⚖️  Council of Agents Worker Started...")
    
    while True:
        try:
            tickers = get_active_tickers()
            if not tickers:
                print("   No active tickers. Sleeping 60s...")
                time.sleep(60)
                continue

            print(f"\n🔄 Starting Council Cycle for {len(tickers)} tickers...")
            
            for ticker in tickers:
                if needs_update(ticker):
                    print(f"   🏛️  Convening Council for {ticker}...")
                    
                    # Execute the actual AI debate
                    result = run_council(ticker)
                    
                    if result.get('verdict') != 'ERROR':
                        print(f"      ✅ Verdict Reached: {result.get('verdict')} (Conf: {result.get('confidence')})")
                    else:
                        print("      ❌ Council failed to reach a verdict.")
                    
                    # Brief pause to manage LLM load
                    time.sleep(5)
                else:
                    time.sleep(0.1)

            print("💤 Cycle complete. Sleeping 5 minutes before re-checking...")
            time.sleep(300)

        except KeyboardInterrupt:
            print("🛑 Worker stopping...")
            break
        except Exception as e:
            print(f"❌ Worker Critical Error: {e}")
            time.sleep(30)

if __name__ == "__main__":
    run_continuous_council()