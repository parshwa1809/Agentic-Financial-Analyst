import os
import sys

# --- FIX: Ensure project root is on sys.path for worker imports ---
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
# -----------------------------------------------------------------

import time
import requests
import pandas as pd
import json
from datetime import datetime, timedelta
from services.db_manager import get_engine, execute_many
from services.redis_lock import acquire_lock, release_lock
from services.redis_manager import get_redis_client
from sqlalchemy import text

# Optional fallback to yfinance
try:
    import yfinance as yf
    _HAVE_YFINANCE = True
except Exception:
    _HAVE_YFINANCE = False

API_KEY = os.getenv("ALPACA_API_KEY")
API_SECRET = os.getenv("ALPACA_API_SECRET")
BASE_URL = os.getenv("ALPACA_BASE_URL", "https://data.alpaca.markets")

engine = get_engine()
DEFAULT_LIMIT = 1000

def _headers():
    return {
        'APCA-API-KEY-ID': API_KEY,
        'APCA-API-SECRET-KEY': API_SECRET,
        'Content-Type': 'application/json'
    }

def _iso(dt: datetime):
    return dt.isoformat() + 'Z'

def fetch_bars_for_symbol(symbol: str, start: datetime, end: datetime, timeframe: str = '5Min'):
    url = f"{BASE_URL}/v2/stocks/{symbol}/bars"
    headers = _headers()
    params = {
        'start': _iso(start),
        'end': _iso(end),
        'timeframe': timeframe,
        'limit': DEFAULT_LIMIT
    }

    backoff = 1
    page_token = None
    while True:
        if page_token:
            params['page_token'] = page_token

        try:
            resp = requests.get(url, headers=headers, params=params, timeout=30)
        except requests.RequestException as e:
            print(f"Request error for {symbol}: {e}. Backing off {backoff}s")
            time.sleep(backoff)
            backoff = min(backoff * 2, 60)
            continue

        if resp.status_code == 200:
            backoff = 1
            data = resp.json()
            bars = data.get('bars') or []
            if not bars:
                return

            yield bars
            page_token = data.get('next_page_token')
            if not page_token:
                return

        elif resp.status_code == 429:
            ra = resp.headers.get('Retry-After')
            wait = int(ra) if ra and ra.isdigit() else backoff
            print(f"Rate limited by Alpaca for {symbol}. Sleeping {wait}s")
            time.sleep(wait)
            backoff = min(backoff * 2, 60)
            continue
        elif resp.status_code == 403:
            raise PermissionError(resp.text or f"403 fetching {symbol} bars")
        else:
            print(f"Error fetching {symbol} bars: {resp.status_code} {resp.text}")
            return

def bars_to_dataframe(bars, symbol: str):
    rows = []
    for b in bars:
        ts = b.get('t') or b.get('timestamp')
        o = b.get('o') or b.get('open')
        h = b.get('h') or b.get('high')
        l = b.get('l') or b.get('low')
        c = b.get('c') or b.get('close')
        v = b.get('v') or b.get('volume')
        rows.append({
            'ticker': symbol,
            'timestamp': pd.to_datetime(ts),
            'open': o,
            'high': h,
            'low': l,
            'close': c,
            'volume': v
        })

    return pd.DataFrame(rows)

def _upsert_market_data(df: pd.DataFrame):
    if df.empty:
        return 0
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    df = df.drop_duplicates(subset=['ticker', 'timestamp'])

    rows = []
    for _, r in df.iterrows():
        rows.append({
            'ticker': r['ticker'],
            'timestamp': r['timestamp'].to_pydatetime(),
            'open': float(r['open']) if pd.notnull(r['open']) else None,
            'high': float(r['high']) if pd.notnull(r['high']) else None,
            'low': float(r['low']) if pd.notnull(r['low']) else None,
            'close': float(r['close']) if pd.notnull(r['close']) else None,
            'volume': int(r['volume']) if pd.notnull(r['volume']) else None,
        })

    query = (
        "INSERT INTO market_data (ticker, timestamp, open, high, low, close, volume) "
        "VALUES (:ticker, :timestamp, :open, :high, :low, :close, :volume) "
        "ON DUPLICATE KEY UPDATE open=VALUES(open), high=VALUES(high), low=VALUES(low), close=VALUES(close), volume=VALUES(volume)"
    )

    execute_many(query, rows)
    return len(rows)

def backfill_tickers(tickers, days=30, timeframe='5Min', chunk_sleep=0.25):
    if not API_KEY or not API_SECRET:
        print("ALPACA_API_KEY and ALPACA_API_SECRET must be set in environment")
        return

    # FIX: Subtract 20 minutes to respect the 15-min delay on Free Plans
    end = datetime.utcnow() - timedelta(minutes=20)

    # Cap high-frequency requests to 30 days
    try:
        max_high_freq = int(os.getenv('BACKFILL_MAX_DAYS_FOR_HIGH_FREQ', '30'))
    except Exception:
        max_high_freq = 30

    high_freq = timeframe in ('1Min', '5Min')
    if high_freq and days > max_high_freq:
        print(f"Reducing days from {days} to {max_high_freq} for high-frequency timeframe {timeframe}")
        days = max_high_freq

    default_start = end - timedelta(days=days)

    for symbol in tickers:
        lock_key = f"backfill:lock:{symbol}"
        lock_ttl = int(os.getenv('BACKFILL_LOCK_TTL', str(60*60*6)))

        token = acquire_lock(lock_key, ttl=lock_ttl)
        if not token:
            print(f"Skipping {symbol}: backfill already in progress on another worker")
            continue

        try:
            pages = 0
            total_rows = 0
            start = default_start

            # Determine start based on existing DB data: backfill gap from last timestamp
            try:
                from sqlalchemy import text as _text
                with engine.connect() as conn:
                    res = conn.execute(
                        _text("SELECT MAX(timestamp) as last_ts FROM market_data WHERE ticker=:t"),
                        {"t": symbol}
                    ).fetchone()
                    last_ts = res[0] if res and res[0] else None

                    if last_ts:
                        # Advance one timeframe unit past last_ts to avoid overlap
                        if timeframe == '1Min': delta = timedelta(minutes=1)
                        elif timeframe == '5Min': delta = timedelta(minutes=5)
                        elif timeframe.lower().startswith('1h') or timeframe == '1Hour': delta = timedelta(hours=1)
                        else: delta = timedelta(days=1)
                        
                        candidate_start = pd.to_datetime(last_ts) + delta
                        if candidate_start < end:
                            start = candidate_start
                        else:
                            print(f"No new data to backfill for {symbol} (last_ts >= now)")
                            start = None
            except Exception as e:
                print(f"Failed to read last timestamp for {symbol}: {e}")

            if start is None:
                continue

            print(f"▶ Backfilling {symbol} from {start} to {end} timeframe={timeframe}")
            
            # Primary attempt using Alpaca
            attempted_timeframe = timeframe
            try:
                for bars in fetch_bars_for_symbol(symbol, start, end, timeframe=attempted_timeframe):
                    pages += 1
                    df = bars_to_dataframe(bars, symbol)
                    if not df.empty:
                        saved = _upsert_market_data(df)
                        total_rows += saved
                        print(f"  ✅ Upserted {saved} bars (page {pages}) for {symbol}")
                    time.sleep(chunk_sleep)

            except PermissionError as perr:
                print(f"Alpaca permission error for {symbol} at {attempted_timeframe}: {perr}")

            # If we have no rows, try yfinance as a last resort
            if total_rows == 0 and _HAVE_YFINANCE:
                try:
                    print(f"Attempting yfinance fallback for {symbol} (timeframe={attempted_timeframe})")
                    yf_start = start.strftime('%Y-%m-%d')
                    yf_end = end.strftime('%Y-%m-%d')
                    yf_interval = {'1Min': '1m', '5Min': '5m', '1Hour': '60m'}.get(attempted_timeframe, '1d')
                    yf_df = yf.download(symbol, start=yf_start, end=yf_end, interval=yf_interval, progress=False, threads=False)

                    if yf_df is not None and not yf_df.empty:
                        yf_df.columns = [c.lower() for c in yf_df.columns]
                        bars = [{'t': pd.to_datetime(idx).to_pydatetime(), 'o': row['open'], 'h': row['high'], 'l': row['low'], 'c': row['close'], 'v': row['volume']} for idx, row in yf_df.iterrows()]
                        
                        if bars:
                            df = bars_to_dataframe(bars, symbol)
                            saved = _upsert_market_data(df)
                            total_rows += saved
                            pages += 1
                            print(f"  ✅ yfinance upserted {saved} bars for {symbol}")
                        
                except Exception as ye:
                    print(f"yfinance fallback failed for {symbol}: {ye}")

        except Exception as e:
            print(f"Error while backfilling {symbol}: {e}")
        finally:
            try:
                release_lock(lock_key, token)
            except Exception:
                pass
            print(f"◾ {symbol} backfill complete — pages={pages}, rows={total_rows}")

if __name__ == '__main__':
    import argparse

    p = argparse.ArgumentParser()
    p.add_argument('--tickers', help='Comma separated tickers or leave empty to use active tickers from DB')
    p.add_argument('--days', type=int, default=30)
    p.add_argument('--timeframe', default='5Min', help='Alpaca timeframe (1Min, 5Min, 1Hour, 1Day)')
    p.add_argument('--chunk-sleep', type=float, default=0.25, help='Delay between page requests to avoid rate limits')
    args = p.parse_args()

    if args.tickers:
        symbols = [s.strip().upper() for s in args.tickers.split(',') if s.strip()]
    else:
        # load active tickers from DB
        import pandas as pd
        from services.db_manager import get_engine
        eng = get_engine()
        try:
            df = pd.read_sql("SELECT symbol FROM tickers WHERE is_active=1", eng)
            symbols = df['symbol'].tolist()
        except Exception as e:
            print(f"Failed to load active tickers from DB: {e}")
            symbols = []

    if not symbols:
        print("No tickers to backfill. Exiting.")
    else:
        backfill_tickers(symbols, days=args.days, timeframe=args.timeframe, chunk_sleep=args.chunk_sleep)