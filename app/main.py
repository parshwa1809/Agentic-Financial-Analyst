from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import os
import pandas as pd

# Import Routers
from app.routers import market, tickers, chat, council, debug

# Services
from services.db_manager import get_engine, execute_query
from services.redis_manager import get_redis_client
from services.backfill_alpaca import backfill_tickers
from rq import Queue

app = FastAPI(title="AI Stock Agent API", version="2.0")

# --- CORS CONFIGURATION ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- REGISTER ROUTERS ---
app.include_router(market.router, prefix="/api/market", tags=["Market Data"])
app.include_router(tickers.router, prefix="/api/tickers", tags=["Tickers"])
app.include_router(chat.router, prefix="/api/chat", tags=["AI Agent"])
app.include_router(council.router, prefix="/api/council", tags=["Agent Council"])
app.include_router(debug.router, prefix="/api/debug", tags=["Debug"])

@app.get("/")
def health_check():
    return {"status": "online", "system": "AI Stock Agent v2"}

@app.on_event("startup")
def on_startup():
    print("🚀 API Starting up...")
    print("✅ Routers loaded: Market, Tickers, Chat, Council, Debug")

    # Check if we should backfill on startup
    if os.getenv('BACKFILL_ON_STARTUP', '0') != '1':
        return

    print("🔄 Initiating Startup Backfill...")
    try:
        eng = get_engine()
        
        # 1. Get Active Tickers
        try:
            df = pd.read_sql("SELECT symbol FROM tickers WHERE is_active=1", eng)
        except Exception as e:
            print(f"⚠️ Failed to load active tickers: {e}")
            return

        symbols = df['symbol'].tolist() if not df.empty else []
        if not symbols:
            print("   No active tickers to backfill.")
            return

        # 2. Configuration (Strict 30 Days)
        days = int(os.getenv('BACKFILL_DAYS', '30')) # Default to 30
        timeframe = os.getenv('BACKFILL_ON_STARTUP_TIMEFRAME', '5Min') # Default to 5Min for charts

        print(f"   Queueing backfill for {len(symbols)} tickers (Days: {days}, TF: {timeframe})")

        # 3. Send to Worker
        try:
            redis_conn = get_redis_client()
            q = Queue(connection=redis_conn)
            
            # Enqueue the job
            q.enqueue(
                backfill_tickers, 
                symbols, 
                days, 
                timeframe, 
                0.5, # chunk sleep
                job_timeout='1h'
            )

            # Log job status to DB
            for s in symbols:
                try:
                    execute_query(
                        "INSERT INTO backfill_jobs (ticker, status, started_at, rows_inserted) VALUES (:t, 'queued', NOW(), 0)", 
                        {"t": s}
                    )
                except: pass
                
            print("✅ Startup backfill jobs enqueued successfully.")
            
        except Exception as e:
            print(f"❌ Failed to enqueue startup backfill: {e}")
            
    except Exception as e:
        print(f"❌ Startup Error: {e}")