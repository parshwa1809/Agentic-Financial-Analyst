from fastapi import APIRouter, HTTPException
from services.db_manager import execute_query, get_engine
from services.redis_manager import get_redis_client
from rq import Queue
import pandas as pd

router = APIRouter()
engine = get_engine()

# Connect to Redis
r = get_redis_client()
queue = Queue(connection=r)

@router.get("/active")
def get_active_tickers():
    try:
        df = pd.read_sql("SELECT symbol, name FROM tickers WHERE is_active=1 ORDER BY symbol", engine)
        return df.to_dict(orient="records")
    except: return []

@router.get("/search")
def search_tickers(q: str):
    try:
        clean = q.replace("'", "").upper()
        # Simple fuzzy search
        df = pd.read_sql(f"SELECT symbol, name, is_active FROM tickers WHERE symbol LIKE '%%{clean}%%' OR UPPER(name) LIKE '%%{clean}%%' LIMIT 10", engine)
        return df.to_dict(orient="records")
    except: return []

@router.get("/all")
def list_all_tickers():
    try:
        df = pd.read_sql("SELECT symbol, name, is_active FROM tickers ORDER BY symbol", engine)
        return df.to_dict(orient="records")
    except Exception:
        return []

@router.post("/{symbol}/activate")
def activate_ticker(symbol: str):
    symbol = symbol.upper()
    print(f"🚀 Activating {symbol}...")

    # 1. Update Database
    try:
        execute_query("UPDATE tickers SET is_active=1 WHERE symbol=:s", {"s": symbol})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    # 2. Enqueue Background Jobs
    # NOTE: Imports are inside the function to prevent "Circular Import" crashes on startup
    try:
        from services.backfill_alpaca import backfill_tickers
        from services.news_fetcher import fetch_news_for_symbols
        
        # Job A: Price Backfill (Strict 30 Days)
        queue.enqueue(
            backfill_tickers, 
            [symbol], 
            days=30,           # Force 30 days as per policy
            timeframe='5Min',  # Ensure 5Min candles for chart
            chunk_sleep=0.5, 
            job_timeout='10m'
        )

        # Job B: News Fetch (Immediate)
        queue.enqueue(
            fetch_news_for_symbols, 
            [symbol], 
            job_timeout='2m'
        )
        
        print(f"✅ Queued Backfill & News for {symbol}")
        
    except ImportError as e:
        print(f"❌ Worker Import Error: {e}")
        # We don't crash the request, but we log the error
    except Exception as e:
        print(f"❌ Queue Error: {e}")

    return {"status": "success", "backfill_scheduled": True}

@router.post("/{symbol}/deactivate")
def deactivate_ticker(symbol: str):
    symbol = symbol.upper()
    execute_query("UPDATE tickers SET is_active=0 WHERE symbol=:s", {"s": symbol})
    return {"status": "success"}