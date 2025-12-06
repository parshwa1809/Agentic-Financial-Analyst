import time
import json
import pandas as pd
import numpy as np
import sys
import os

# --- FIX: Add Project Root to Path ---
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
# -------------------------------------

from services.redis_manager import get_redis_client
from services.db_manager import get_engine, execute_query
from services.indicators import calculate_rsi, calculate_bbands, calculate_vwap

# Connect to Redis
r = get_redis_client()
engine = get_engine()

# Configuration
CONTEXT = os.getenv("CONTEXT_TICKERS", "SPY,^VIX").split(",")

def get_window(ticker):
    """Fetch the last 100 bars from Redis sliding window."""
    try:
        # Redis returns bytes, so we need to decode
        raw = r.zrange(f"window:{ticker}", 0, -1)
        if not raw: return None
        
        # Decode bytes to strings, then load JSON
        data = [json.loads(x.decode('utf-8')) for x in raw]
        df = pd.DataFrame(data)
        
        # Ensure numeric types
        df['close'] = pd.to_numeric(df['close'])
        df['volume'] = pd.to_numeric(df['volume'])
        return df
    except Exception as e:
        print(f"⚠️ Error reading window for {ticker}: {e}")
        return None

def check_technical_signals(df, ticker):
    """Check for RSI, Bollinger Bands, and Price Spikes."""
    alerts = []
    try:
        if len(df) < 20: return []
        
        current_price = df['close'].iloc[-1]
        prev_price = df['close'].iloc[-2]
        
        # 1. RSI Logic
        rsi = calculate_rsi(df['close'], 14).iloc[-1]
        if rsi < 30:
            alerts.append(f"Technical: RSI Oversold ({rsi:.1f}) - Potential Buy")
        elif rsi > 70:
            alerts.append(f"Technical: RSI Overbought ({rsi:.1f}) - Potential Sell")
            
        # 2. Bollinger Bands Logic
        upper, sma, lower = calculate_bbands(df['close'])
        if current_price < lower.iloc[-1]:
            alerts.append(f"Technical: Price broke below Lower Bollinger Band (${current_price:.2f})")
        elif current_price > upper.iloc[-1]:
            alerts.append(f"Technical: Price broke above Upper Bollinger Band (${current_price:.2f})")
            
        # 3. Sudden Price Spike (> 2% in 5 mins)
        lookback_price = df['close'].iloc[-5] if len(df) >= 5 else prev_price
        pct_change = ((current_price - lookback_price) / lookback_price) * 100
        
        if pct_change > 2.0:
            alerts.append(f"Volatility: 🚀 Sudden Price Spike (+{pct_change:.2f}%)")
        elif pct_change < -2.0:
            alerts.append(f"Volatility: 🔻 Sudden Price Drop ({pct_change:.2f}%)")
            
    except Exception as e:
        print(f"Tech Check Error {ticker}: {e}")
        
    return alerts

def check_volume_signals(df, ticker):
    """Check for unusual volume spikes."""
    alerts = []
    try:
        if len(df) < 20: return []
        
        current_vol = df['volume'].iloc[-1]
        avg_vol = df['volume'].rolling(20).mean().iloc[-1]
        
        if avg_vol > 0 and current_vol > (avg_vol * 3):
            alerts.append(f"Volume: 📢 Massive Volume Spike ({int(current_vol)} vs Avg {int(avg_vol)})")
        elif avg_vol > 0 and current_vol > (avg_vol * 2):
            alerts.append(f"Volume: Unusual Volume Detected (2x Average)")
            
    except Exception as e:
        print(f"Vol Check Error {ticker}: {e}")
        
    return alerts

def process_alerts():
    print("🚨 Alert Engine Active... Monitoring Redis Windows")
    while True:
        try:
            # 1. Find all active tickers with data in Redis
            keys = r.keys("window:*")
            
            for key in keys:
                ticker = key.decode('utf-8').split(":")[1]
                
                # Skip context tickers if needed, or process them too
                if ticker in CONTEXT: continue

                df = get_window(ticker)
                if df is None or df.empty: continue
                
                # 2. Run Checks
                alerts = []
                alerts.extend(check_technical_signals(df, ticker))
                alerts.extend(check_volume_signals(df, ticker))
                
                # 3. Save to Database
                for msg in alerts:
                    print(f"🔔 ALERT {ticker}: {msg}")
                    try:
                        execute_query(
                            "INSERT INTO active_alerts (ticker, message, created_at) VALUES (:t, :m, NOW())", 
                            {"t": ticker, "m": msg}
                        )
                        # Optional: Sleep briefly to avoid spamming duplicate alerts instantly
                        # A better deduplication strategy would be checking DB for recent similar alerts
                    except Exception as db_err:
                        print(f"❌ DB Error saving alert: {db_err}")

        except Exception as e:
            print(f"❌ Main Loop Error: {e}")
        
        time.sleep(5) # Check every 5 seconds

if __name__ == "__main__":
    # Wait for DB/Redis to be ready
    time.sleep(10)
    process_alerts()