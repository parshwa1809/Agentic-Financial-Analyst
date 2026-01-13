import os
import sys
import alpaca_trade_api as tradeapi
from dotenv import load_dotenv
from sqlalchemy import text
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from services.db_manager import engine # Import Engine directly for safety

load_dotenv()

def seed():
    print("🌍 Fetching Market Universe (Stocks Only)...")
    
    # 1. Connect to Alpaca
    try:
        api = tradeapi.REST(
            os.getenv("ALPACA_KEY"), 
            os.getenv("ALPACA_SECRET"), 
            base_url=os.getenv("APCA_API_BASE_URL")
        )
        assets = api.list_assets(status='active', asset_class='us_equity')
        print(f"📦 Found {len(assets)} stocks. Starting import...")
    except Exception as e:
        print(f"❌ Alpaca Error: {e}")
        return

    # 2. Batch Insert with Commit
    count = 0
    with engine.connect() as conn:
        for a in assets:
            try:
                # Insert as INACTIVE (is_active=0)
                conn.execute(
                    text("INSERT IGNORE INTO tickers (symbol, name, is_active) VALUES (:s, :n, 0)"), 
                    {"s": a.symbol, "n": a.name}
                )
                count += 1
                
                # Commit every 100 rows to be safe
                if count % 100 == 0:
                    conn.commit()
                    print(f"   ...saved {count} tickers")
            except Exception as e:
                pass
        
        conn.commit() # Final commit
        
    print(f"✅ SUCCESS: {count} tickers seeded into Database (All Inactive).")

if __name__ == "__main__":
    seed()