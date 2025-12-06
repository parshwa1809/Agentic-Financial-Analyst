import pandas as pd
import numpy as np
import math
from fastapi import APIRouter, HTTPException
from datetime import datetime, timedelta
from sqlalchemy import text
from services.db_manager import get_engine
from services.indicators import calculate_rsi, calculate_bbands, calculate_vwap, calculate_macd, calculate_bandwidth

router = APIRouter()
engine = get_engine()

def format_number(num):
    """Safely format numbers for the Stats panel."""
    if num is None: return "N/A"
    try:
        val = float(num)
        if math.isnan(val) or math.isinf(val): return "N/A"
    except: return "N/A"
    
    if val >= 1e12: return f"${val/1e12:.2f}T"
    if val >= 1e9: return f"${val/1e9:.2f}B"
    if val >= 1e6: return f"${val/1e6:.2f}M"
    return f"{val:.2f}"

@router.get("/{ticker}/candles")
def get_candles(ticker: str, timeframe: str = "1D"):
    ticker = ticker.upper()
    print(f"📊 Fetching candles for {ticker} ({timeframe})...")
    
    mapping = {'1D': 1, '1W': 7, '1M': 30}
    days = mapping.get(timeframe, 30)
    
    try:
        # --- FIX: GET LATEST DATA POINT FIRST ---
        # Instead of subtracting from "NOW()", we subtract from the "Last Candle Time".
        # This ensures that viewing "1D" on a Saturday correctly shows all of Friday.
        latest_query = text("SELECT MAX(timestamp) as last_ts FROM market_data WHERE ticker = :t")
        latest_df = pd.read_sql(latest_query, engine, params={"t": ticker})
        
        if not latest_df.empty and latest_df.iloc[0]['last_ts']:
            latest_ts = pd.to_datetime(latest_df.iloc[0]['last_ts'])
        else:
            latest_ts = datetime.utcnow() # Fallback if no data exists
            
        # Calculate start date relative to the latest data
        cutoff = latest_ts - timedelta(days=days)
        # ----------------------------------------

        query = text("""
            SELECT ticker, timestamp, open, high, low, close, volume 
            FROM market_data 
            WHERE ticker = :t 
            AND timestamp >= :c 
            ORDER BY timestamp ASC
        """)
        
        df = pd.read_sql(query, engine, params={"t": ticker, "c": cutoff})
        
        if df.empty: 
            return {"data": []}
        
        # Calculate Indicators
        try:
            df['RSI'] = calculate_rsi(df['close'], 14)
            upper, middle, lower = calculate_bbands(df['close'])
            df['BBU_20_2.0'] = upper
            df['BBL_20_2.0'] = lower
            df['BandWidth'] = calculate_bandwidth(upper, lower, middle)
            df['VWAP'] = calculate_vwap(df)
            macd_line, _ = calculate_macd(df['close'])
            df['MACD'] = macd_line
        except Exception as e:
            print(f"   Indicator Warning: {e}")

        # Data Sanitization
        df['timestamp'] = df['timestamp'].astype(str)
        df = df.astype(object)
        df.where(pd.notnull(df), None, inplace=True)
        df.replace([np.inf, -np.inf], None, inplace=True)
        
        return {"data": df.to_dict(orient="records")}
        
    except Exception as e:
        print(f"❌ API Error (Candles): {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ... (Keep get_stats, get_recent_alerts, get_market_news, get_supply_chain exactly as they were) ...
@router.get("/{ticker}/stats")
def get_stats(ticker: str):
    ticker = ticker.upper()
    try:
        fund_query = text("SELECT * FROM fundamentals WHERE ticker=:t")
        risk_query = text("SELECT AVG(risk_score) as score FROM political_risk WHERE ticker=:t")
        
        fund = pd.read_sql(fund_query, engine, params={"t": ticker})
        risk = pd.read_sql(risk_query, engine, params={"t": ticker})
        
        stats = {"risk_score": 0, "ratios": []}

        if not risk.empty and pd.notnull(risk.iloc[0]['score']):
            try:
                val = float(risk.iloc[0]['score'])
                if not (math.isnan(val) or math.isinf(val)):
                    stats['risk_score'] = round(val, 1)
            except: pass

        if not fund.empty:
            row = fund.iloc[0]
            mappings = [
                ("market_cap", "Market Cap", "currency"),
                ("pe_ratio", "P/E Ratio", "number"),
                ("pb_ratio", "P/B Ratio", "number"),
                ("ps_ratio", "P/S Ratio", "number"),
                ("debt_to_equity", "Debt/Eq", "number"),
                ("profit_margin", "Margins", "percent"),
                ("dividend_yield", "Div Yield", "percent"),
                ("eps_ttm", "EPS (TTM)", "currency_val"),
            ]
            
            for col, label, fmt in mappings:
                val = row.get(col)
                display_val = "N/A"
                if val is not None:
                    try:
                        f_val = float(val)
                        if not (math.isnan(f_val) or math.isinf(f_val)):
                            if fmt == "currency": display_val = format_number(f_val)
                            elif fmt == "percent": display_val = f"{f_val*100:.2f}%"
                            elif fmt == "currency_val": display_val = f"${f_val:.2f}"
                            else: display_val = f"{f_val:.2f}"
                    except: pass
                
                stats['ratios'].append({"label": label, "value": display_val, "key": col})

        return stats
    except Exception as e:
        print(f"❌ API Error (Stats): {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/alerts")
def get_recent_alerts(ticker: str = None):
    try:
        if ticker:
            ticker = ticker.upper()
            query = text("SELECT ticker, message, created_at FROM active_alerts WHERE ticker=:t ORDER BY created_at DESC LIMIT 50")
            df = pd.read_sql(query, engine, params={"t": ticker})
        else:
            query = text("SELECT ticker, message, created_at FROM active_alerts ORDER BY created_at DESC LIMIT 50")
            df = pd.read_sql(query, engine)
        
        if not df.empty and 'created_at' in df.columns:
            df['created_at'] = df['created_at'].astype(str)
            
        return df.to_dict(orient="records")
    except Exception as e:
        print(f"❌ API Error (Alerts): {e}")
        return []

@router.get("/news")
def get_market_news(ticker: str = None):
    try:
        if ticker:
            ticker = ticker.upper()
            query = text("SELECT ticker, headline, url, published_at, sentiment_score FROM news_articles WHERE ticker=:t ORDER BY published_at DESC LIMIT 10")
            params = {"t": ticker}
        else:
            query = text("SELECT ticker, headline, url, published_at, sentiment_score FROM news_articles ORDER BY published_at DESC LIMIT 10")
            params = {}
        
        df = pd.read_sql(query, engine, params=params)
        
        if not df.empty and 'published_at' in df.columns:
            df['published_at'] = df['published_at'].astype(str)
            
        return df.to_dict(orient="records")
    except Exception as e:
        print(f"❌ API Error (News): {e}")
        return []

@router.get("/{ticker}/supply-chain")
def get_supply_chain(ticker: str):
    ticker = ticker.upper()
    try:
        query = text("SELECT * FROM supply_chain WHERE ticker=:t")
        df = pd.read_sql(query, engine, params={"t": ticker})
        
        if df.empty: return {"nodes": [], "links": []}
        
        nodes = [{"id": ticker, "type": "TARGET"}]
        links = []
        seen = {ticker}
        for _, row in df.iterrows():
            partner = row['partner_ticker']
            if partner not in seen:
                nodes.append({"id": partner, "type": row['relationship']})
                seen.add(partner)
            links.append({"source": ticker, "target": partner, "type": row['relationship']})
        return {"nodes": nodes, "links": links}
    except Exception as e:
        print(f"❌ API Error (Supply Chain): {e}")
        return {"nodes": [], "links": []} 