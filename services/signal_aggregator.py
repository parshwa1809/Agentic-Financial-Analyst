import pandas as pd
from sqlalchemy import text
from services.db_manager import get_engine

# --- THE FIX IS HERE ---
# We now import from 'services.signals' instead of just 'services'
from services.signals import technical, volume, calendar, market_context

engine = get_engine()

def get_market_data(ticker, limit=100):
    """Fetches the last N candles for a ticker."""
    query = text("SELECT * FROM market_data WHERE ticker=:t ORDER BY timestamp ASC LIMIT :l")
    with engine.connect() as conn:
        df = pd.read_sql(query, conn, params={"t": ticker, "l": limit})
    return df

def get_active_signals(ticker):
    """
    Runs ALL signal files and aggregates alerts.
    """
    alerts = []
    
    # 1. Fetch Data
    df = get_market_data(ticker)
    if df.empty: return []

    # Optional: Fetch SPY/VIX for context if needed
    spy_df = pd.DataFrame() 
    vix_df = pd.DataFrame()

    # 2. Run Each Signal Module
    # We wrap in try/except so one bad file doesn't crash the whole system
    try:
        alerts.extend(technical.compute_signals(df, ticker))
    except Exception as e: print(f"⚠️ Technical Signal Error: {e}")

    try:
        alerts.extend(volume.compute_signals(df, ticker))
    except Exception as e: print(f"⚠️ Volume Signal Error: {e}")

    try:
        alerts.extend(calendar.compute_signals(df, ticker))
    except Exception as e: print(f"⚠️ Calendar Signal Error: {e}")

    try:
        alerts.extend(market_context.compute_signals(df, ticker, spy_df, vix_df))
    except Exception as e: print(f"⚠️ Context Signal Error: {e}")

    return alerts