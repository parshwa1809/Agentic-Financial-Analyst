import re
import sys
import os
import threading
import asyncio
import time
import json
import pandas as pd
from alpaca_trade_api.stream import Stream
from sqlalchemy import text

# Ensure project root is on sys.path
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from services.redis_manager import get_redis_client
from services.db_manager import get_engine
from services.heartbeat import beat

ALPACA_KEY = os.getenv("ALPACA_KEY")
ALPACA_SECRET = os.getenv("ALPACA_SECRET")

# Connect to Redis & DB
redis_client = get_redis_client()
engine = get_engine()

current_stream = None
stream_thread = None
_last_bar_beat = 0.0

def get_ecosystem_tickers():
    """
    Fetches the 'Active Universe' for Price Streaming:
    1. Tickers marked as Active (Your Watchlist).
    2. Any partner (Supplier/Customer/Competitor) linked to an Active ticker.
    """
    try:
        # 1. Get Active Tickers
        df_active = pd.read_sql("SELECT symbol FROM tickers WHERE is_active = 1", engine)
        active_set = set(df_active['symbol'].tolist()) if not df_active.empty else set()
        
        if not active_set:
            return []

        # 2. Get Partners of Active Tickers
        # Only fetch partners relevant to what we are currently watching
        partner_query = text("""
            SELECT DISTINCT partner_ticker 
            FROM supply_chain 
            WHERE ticker IN (SELECT symbol FROM tickers WHERE is_active=1)
        """)
        
        # Execute safely using SQLAlchemy engine
        with engine.connect() as conn:
            partner_rows = conn.execute(partner_query).fetchall()
            
        partner_set = set(r[0] for r in partner_rows) if partner_rows else set()

        # 3. Combine and Deduplicate
        full_universe = list(active_set.union(partner_set))
        
        # Filter out junk
        blacklist = {"UNKNOWN", "NONE", "NULL", "TBA", "VARIOUS", "N/A"}
        full_universe = [t for t in full_universe if t and t.upper() not in blacklist and len(t) < 10]

        # Alpaca's stream rejects the whole subscription (400 "invalid syntax") if ANY
        # symbol is malformed, so keep only US-style tickers (e.g. AAPL, BRK.B) and log the rest.
        valid_re = re.compile(r"^[A-Z]{1,5}(\.[A-Z]{1,2})?$")
        skipped = [t for t in full_universe if not valid_re.match(t.strip())]
        full_universe = [t.strip() for t in full_universe if valid_re.match(t.strip())]
        if skipped:
            print(f"⚠️ Skipping {len(skipped)} symbols Alpaca can't stream: {sorted(skipped)}")
        
        # Alpaca's free (Basic) plan allows 30 WebSocket symbols. Watchlist tickers always go
        # first; partners fill the remaining slots. Raise ALPACA_MAX_SYMBOLS on a paid plan.
        cap = int(os.getenv("ALPACA_MAX_SYMBOLS", "30"))
        active_first = sorted(t for t in full_universe if t in active_set)
        partners = sorted(t for t in full_universe if t not in active_set)
        final_list = (active_first + partners)[:cap]
        if len(full_universe) > cap:
            print(f"ℹ️ Streaming {cap} of {len(full_universe)} symbols (plan limit); {len(full_universe) - cap} partners skipped")
        
        # DEBUG PRINT
        print(f"📋 Ecosystem Price Target: {len(active_set)} Active + {len(partner_set)} Partners = {len(final_list)} Total")
        return final_list

    except Exception as e:
        print(f"❌ DB Error fetching tickers: {e}")
        return []

async def bar_handler(bar):
    """Handle incoming price bars."""
    try:
        # Normalize attributes (Alpaca library sometimes uses short keys)
        symbol = getattr(bar, 'symbol', None) or getattr(bar, 'S', 'UNKNOWN')
        close_price = getattr(bar, 'close', None) or getattr(bar, 'c', 0.0)
        volume = getattr(bar, 'volume', None) or getattr(bar, 'v', 0)
        timestamp = getattr(bar, 'timestamp', None) or getattr(bar, 't', str(time.time()))
        
        # DEBUG PRINT (Only print Active tickers to keep logs clean, or all if debugging)
        # print(f"📥 {symbol} @ ${close_price} (Vol: {volume})")

        data = {
            "ticker": symbol,
            "timestamp": str(timestamp),
            "price": float(close_price),
            "volume": int(volume),
            "close": float(close_price),
            "open": float(getattr(bar, 'open', 0) or getattr(bar, 'o', 0)),
            "high": float(getattr(bar, 'high', 0) or getattr(bar, 'h', 0)),
            "low": float(getattr(bar, 'low', 0) or getattr(bar, 'l', 0)),
        }
        json_data = json.dumps(data)
        
        # 1. Push to DB Writer (Saves to 'market_data' table)
        redis_client.rpush("trade_queue", json_data)
        
        # 2. Push to Alert Engine (For Real-time Technical Analysis)
        redis_client.zadd(f"window:{symbol}", {json_data: time.time()})
        
        # 3. Trim (Keep last 100 candles in Redis memory)
        redis_client.zremrangebyrank(f"window:{symbol}", 0, -101)

        # 4. Heartbeat (throttled) so the UI can show the stream is really delivering bars
        global _last_bar_beat
        if time.time() - _last_bar_beat > 30:
            _last_bar_beat = time.time()
            beat("price_stream", "ok", f"receiving bars · last {symbol} @ {float(close_price):.2f}")
        
    except Exception as e:
        print(f"❌ Handler Error: {e}")

def start_stream_in_thread(tickers):
    global current_stream
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    print(f"🔌 Connecting to Alpaca for {len(tickers)} tickers...")
    try:
        current_stream = Stream(
            ALPACA_KEY, 
            ALPACA_SECRET, 
            base_url="https://paper-api.alpaca.markets", 
            data_feed='iex' 
        )
        current_stream.subscribe_bars(bar_handler, *tickers)
        current_stream.run()
    except Exception as e:
        print(f"❌ Stream Crash: {e}")
        beat("price_stream", "error", f"stream crashed: {e}")

def run_service():
    global current_stream, stream_thread
    active_tickers = []
    
    print("🚀 Price Ingestion Service Starting (Ecosystem Mode)...")
    
    while True:
        new_tickers = get_ecosystem_tickers()
        
        if not new_tickers:
            print("⚠️ No tickers found in Ecosystem! Waiting...")
            beat("price_stream_subscription", "idle", "no tickers to stream")
        
        # First run (or the stream thread died): start ONE websocket connection.
        # Alpaca's free IEX feed allows only a single concurrent connection, so we
        # never open a second stream; we change subscriptions on the live one instead.
        elif stream_thread is None or not stream_thread.is_alive():
            print(f"🔌 Starting stream for {len(new_tickers)} tickers")
            stream_thread = threading.Thread(target=start_stream_in_thread, args=(new_tickers,), daemon=True)
            stream_thread.start()
            active_tickers = new_tickers

        elif new_tickers != active_tickers:
            added = sorted(set(new_tickers) - set(active_tickers))
            removed = sorted(set(active_tickers) - set(new_tickers))
            print(f"🔄 Ecosystem Changed! +{added} -{removed}")
            try:
                if added:
                    current_stream.subscribe_bars(bar_handler, *added)
                if removed:
                    current_stream.unsubscribe_bars(*removed)
                active_tickers = new_tickers
            except Exception as e:
                print(f"⚠️ Subscription update failed ({e}); will retry next cycle")
        
        if new_tickers:
            beat("price_stream_subscription", "ok", f"subscribed to {len(active_tickers)} tickers", ttl=300)

        # Check for new partners every 30 seconds
        time.sleep(30)

if __name__ == "__main__":
    # Small boot delay to let DB come online
    time.sleep(5)
    run_service()