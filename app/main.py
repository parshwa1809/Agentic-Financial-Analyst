from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routers import council, chat, market, tickers, debug, research, system, alerts, evals

app = FastAPI(title="AI Stock Agent API")

# --- CORS CONFIGURATION ---
# Development: any origin (localhost tools, Vite dev server).
# Production (ORACLE_ENV=production): only the origins listed in ALLOWED_ORIGINS.
import os
PRODUCTION = os.getenv("ORACLE_ENV", "development").lower() == "production"
origins = ([o.strip() for o in os.getenv("ALLOWED_ORIGINS", "http://localhost").split(",") if o.strip()]
           if PRODUCTION else ["*"])

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=PRODUCTION,   # browsers reject credentials with a wildcard origin
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- REGISTER ROUTERS ---
app.include_router(council.router, prefix="/api/council", tags=["Council"])
app.include_router(chat.router, prefix="/api/chat", tags=["Chat"])
app.include_router(market.router, prefix="/api/market", tags=["Market Data"])
app.include_router(tickers.router, prefix="/api/tickers", tags=["Tickers"])
if not PRODUCTION:  # table counts and internals: local use only
    app.include_router(debug.router, prefix="/api/debug", tags=["Debug"])
app.include_router(research.router, prefix="/api/research", tags=["Research"])
app.include_router(system.router, prefix="/api/system", tags=["System"])
app.include_router(alerts.router, prefix="/api/alerts", tags=["Alerts"])
app.include_router(evals.router, prefix="/api/evals", tags=["Evals"])

@app.get("/health")
@app.get("/api/health")
def health_check():
    return {"status": "ok", "message": "System Operational"}