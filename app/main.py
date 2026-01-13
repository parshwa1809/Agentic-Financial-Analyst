from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routers import council, chat, market, tickers

app = FastAPI(title="AI Stock Agent API")

# --- CORS CONFIGURATION ---
# Allows your React Frontend (localhost) to talk to this Backend
origins = [
    "http://localhost",
    "http://localhost:80",
    "http://localhost:3000",
    "http://localhost:5173",
    "*"
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- REGISTER ROUTERS ---
app.include_router(council.router, prefix="/api/council", tags=["Council"])
app.include_router(chat.router, prefix="/api/chat", tags=["Chat"])
app.include_router(market.router, prefix="/api/market", tags=["Market Data"])
app.include_router(tickers.router, prefix="/api/tickers", tags=["Tickers"])

@app.get("/health")
def health_check():
    return {"status": "ok", "message": "System Operational"}