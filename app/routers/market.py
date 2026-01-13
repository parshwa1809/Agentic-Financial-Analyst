import pandas as pd
import numpy as np
import math
from fastapi import APIRouter, HTTPException
from datetime import datetime, timedelta
from sqlalchemy import text
from services.db_manager import get_engine
from services.indicators import calculate_rsi, calculate_bbands, calculate_vwap, calculate_macd, calculate_bandwidth
from services.risk_engine import get_or_compute_risk_score

router = APIRouter()
engine = get_engine()

# --- HELPER: FORMAT NUMBERS ---
def format_number(num):
    if num is None: return "N/A"
    try:
        val = float(num)
        if math.isnan(val) or math.isinf(val): return "N/A"
    except: return "N/A"
    if val >= 1e12: return f"${val/1e12:.2f}T"
    if val >= 1e9: return f"${val/1e9:.2f}B"
    if val >= 1e6: return f"${val/1e6:.2f}M"
    return f"{val:.2f}"

# --- ENDPOINT: CANDLES ---
@router.get("/{ticker}/candles")
def get_candles(ticker: str, timeframe: str = "1D"):
    ticker = ticker.upper()
    mapping = {'1Min': 1, '5Min': 5, '15Min': 7, '1D': 1, '1W': 7, '1M': 30, '3M': 90, '1Y': 365}
    days = mapping.get(timeframe, 30)
    
    try:
        latest_query = text("SELECT MAX(timestamp) as last_ts FROM market_data WHERE ticker = :t")
        latest_df = pd.read_sql(latest_query, engine, params={"t": ticker})
        latest_ts = pd.to_datetime(latest_df.iloc[0]['last_ts']) if not latest_df.empty and latest_df.iloc[0]['last_ts'] else datetime.utcnow() 
        cutoff = latest_ts - timedelta(days=days)

        query = text("SELECT ticker, timestamp, open, high, low, close, volume FROM market_data WHERE ticker = :t AND timestamp >= :c ORDER BY timestamp ASC")
        df = pd.read_sql(query, engine, params={"t": ticker, "c": cutoff})
        
        if df.empty: return {"data": []}
        
        try:
            df['RSI'] = calculate_rsi(df['close'], 14)
            upper, middle, lower = calculate_bbands(df['close'])
            df['BandWidth'] = calculate_bandwidth(upper, lower, middle)
            df['VWAP'] = calculate_vwap(df)
            macd_line, _ = calculate_macd(df['close'])
            df['MACD'] = macd_line
        except Exception: pass

        df['timestamp'] = df['timestamp'].astype(str)
        df = df.astype(object)
        df.where(pd.notnull(df), None, inplace=True)
        return {"data": df.to_dict(orient="records")}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# --- ENDPOINT: STATS ---
@router.get("/{ticker}/stats")
def get_stats(ticker: str):
    ticker = ticker.upper()
    try:
        fund_query = text("SELECT * FROM fundamentals WHERE ticker=:t")
        fund = pd.read_sql(fund_query, engine, params={"t": ticker})
        real_risk_score = get_or_compute_risk_score(ticker)
        stats = {"risk_score": real_risk_score, "ratios": []}

        if not fund.empty:
            row = fund.iloc[0]
            mappings = [("market_cap", "Market Cap", "currency"), ("pe_ratio", "P/E Ratio", "number"), ("pb_ratio", "P/B Ratio", "number"), ("debt_to_equity", "Debt/Eq", "number"), ("profit_margin", "Margins", "percent"), ("dividend_yield", "Div Yield", "percent")]
            for col, label, fmt in mappings:
                val = row.get(col)
                display_val = "N/A"
                if val is not None:
                    try:
                        f_val = float(val)
                        if fmt == "currency": display_val = format_number(f_val)
                        elif fmt == "percent": display_val = f"{f_val*100:.2f}%"
                        else: display_val = f"{f_val:.2f}"
                    except: pass
                stats['ratios'].append({"label": label, "value": display_val, "key": col})
        return stats
    except Exception: return {"risk_score": 50, "ratios": []}

# --- ENDPOINT: ALERTS ---
@router.get("/alerts")
def get_recent_alerts(ticker: str = None):
    try:
        query = text("SELECT ticker, message, created_at FROM active_alerts WHERE ticker=:t ORDER BY created_at DESC LIMIT 50") if ticker else text("SELECT ticker, message, created_at FROM active_alerts ORDER BY created_at DESC LIMIT 50")
        df = pd.read_sql(query, engine, params={"t": ticker.upper()} if ticker else {})
        if not df.empty:
            df['created_at'] = df['created_at'].astype(str)
            return df.to_dict(orient="records")
        return []
    except Exception: return []

# --- ENDPOINT: NEWS ---
@router.get("/news")
def get_market_news(ticker: str = None):
    try:
        query = text("SELECT ticker, headline, url, published_at, sentiment_score FROM news_articles WHERE ticker=:t ORDER BY published_at DESC LIMIT 20") if ticker else text("SELECT ticker, headline, url, published_at, sentiment_score FROM news_articles ORDER BY published_at DESC LIMIT 20")
        df = pd.read_sql(query, engine, params={"t": ticker.upper()} if ticker else {})
        if not df.empty:
            df['published_at'] = df['published_at'].astype(str)
            return df.to_dict(orient="records")
        return []
    except Exception: return []

# --- 3-WAY CATEGORY MAPPING ---
def normalize_relationship(rel_type):
    rel = rel_type.upper().strip()
    if rel in ['CUSTOMER', 'CLIENT', 'OEM', 'DISTRIBUTOR', 'RESELLER', 'BUYER']:
        return 'CUSTOMER'
    if rel in ['COMPETITOR', 'RIVAL', 'PEER', 'CHALLENGER']:
        return 'COMPETITOR'
    return 'SUPPLIER' # Default fallback

# --- FIXED: SUPPLY CHAIN (Deduplicated & Cleaned) ---
@router.get("/{ticker}/supply-chain")
def get_supply_chain(ticker: str):
    ticker = ticker.upper()
    try:
        query = text("SELECT * FROM supply_chain WHERE ticker=:t")
        df = pd.read_sql(query, engine, params={"t": ticker})
        
        if df.empty: return {"nodes": [], "links": []}
        
        nodes = [{"id": ticker, "type": "TARGET"}]
        links = []
        seen_partners = {ticker} # Deduplication Set
        
        # JUNK FILTER
        BLACKLIST = {"UNKNOWN", "NONE", "NULL", "TBA", "VARIOUS", "N/A"}

        for _, row in df.iterrows():
            partner = row['partner_ticker']
            
            # 1. Clean Data Check
            if not partner or str(partner).upper() in BLACKLIST:
                continue
                
            # 2. Map Relationship
            raw_rel = row['relationship']
            display_rel = normalize_relationship(raw_rel)
            
            # 3. Deduplicate
            if partner not in seen_partners:
                nodes.append({"id": partner, "type": display_rel})
                seen_partners.add(partner)
                links.append({"source": ticker, "target": partner, "type": display_rel})
            
        return {"nodes": nodes, "links": links}
    except Exception: return {"nodes": [], "links": []}