from fastapi import APIRouter, HTTPException
from sqlalchemy import text
from services.db_manager import get_engine
from services.redis_manager import get_redis_client
from rq import Queue
import pandas as pd

router = APIRouter()
engine = get_engine()
r = get_redis_client()
queue = Queue(connection=r)

@router.get("/active")
def get_active_tickers():
    try:
        df = pd.read_sql("SELECT symbol, name FROM tickers WHERE is_active=1 ORDER BY symbol", engine)
        return df.to_dict(orient="records")
    except: return []

@router.get("/all")
def list_all_tickers():
    try:
        df = pd.read_sql("SELECT symbol, name, is_active FROM tickers ORDER BY symbol", engine)
        return df.to_dict(orient="records")
    except: return []

@router.get("/search")
def search_tickers(q: str):
    try:
        clean = q.replace("'", "").upper()
        df = pd.read_sql(f"SELECT symbol, name, is_active FROM tickers WHERE symbol LIKE '%%{clean}%%' OR UPPER(name) LIKE '%%{clean}%%' LIMIT 10", engine)
        return df.to_dict(orient="records")
    except: return []

@router.post("/{symbol}/activate")
def activate_ticker(symbol: str):
    symbol = symbol.upper()
    print(f"🛑 API RECEIVED CLICK: Activating {symbol}...", flush=True)

    try:
        with engine.begin() as conn:
            conn.execute(
                text("INSERT INTO tickers (symbol, name, is_active) VALUES (:s, :s, 1) ON DUPLICATE KEY UPDATE is_active=1"),
                {"s": symbol}
            )
            print(f"   ✅ DB Write Successful (Committed) for {symbol}", flush=True)

        with engine.connect() as conn:
            result = conn.execute(text("SELECT is_active FROM tickers WHERE symbol=:s"), {"s": symbol}).fetchone()
            val = result[0] if result else "NULL"
            print(f"   🧐 VERIFICATION: Database says {symbol} is_active = {val}", flush=True)

        try:
            from services.backfill_alpaca import backfill_tickers
            from services.news_fetcher import fetch_news_for_symbols
            from services.seed_supply_chain import discover_partners
            
            queue.enqueue(discover_partners, symbol, job_timeout='2m')
            queue.enqueue(backfill_tickers, [symbol], days=30, timeframe='5Min', chunk_sleep=0.5, job_timeout='10m')
            queue.enqueue(fetch_news_for_symbols, [symbol], job_timeout='2m')
            
            print(f"   🚀 Jobs Queued in Redis for {symbol}", flush=True)
        except ImportError as e:
            print(f"   ⚠️ Job Import Warning: {e}", flush=True)

    except Exception as e:
        print(f"   ❌ CRITICAL ERROR: {e}", flush=True)
        raise HTTPException(status_code=500, detail=str(e))

    return {"status": "success", "symbol": symbol}

@router.post("/{symbol}/deactivate")
def deactivate_ticker(symbol: str):
    symbol = symbol.upper()
    with engine.begin() as conn:
        conn.execute(text("UPDATE tickers SET is_active=0 WHERE symbol=:s"), {"s": symbol})
    return {"status": "success"}