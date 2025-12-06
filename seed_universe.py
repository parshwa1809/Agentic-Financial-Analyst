import os
import sys
import alpaca_trade_api as tradeapi
from dotenv import load_dotenv

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from services.db_manager import execute_query

load_dotenv()

def seed():
    print("🌍 Fetching Market Universe (Stocks Only)...")
    
    # Connect to Alpaca
    api = tradeapi.REST(
        os.getenv("ALPACA_KEY"), 
        os.getenv("ALPACA_SECRET"), 
        base_url=os.getenv("APCA_API_BASE_URL")
    )
    
    # Fetch ONLY Stocks (us_equity)
    assets = api.list_assets(status='active', asset_class='us_equity')
    print(f"📦 Found {len(assets)} stocks. Saving to TiDB...")
    
    count = 0
    for a in assets:
        try:
            # Insert into DB
            execute_query(
                "INSERT IGNORE INTO tickers (symbol, name, is_active) VALUES (:s, :n, 0)", 
                {"s": a.symbol, "n": a.name}
            )
            count += 1
            if count % 1000 == 0: print(f"   ...saved {count}")
        except: pass
        
    print("✅ Done.")

if __name__ == "__main__":
    seed()