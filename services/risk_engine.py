import os
import redis
import json
import pandas as pd
from sqlalchemy import text
from services.db_manager import get_engine, execute_query
# NEW: Import the Aggregator to get text-based alerts
from services.signal_aggregator import get_active_signals

# Redis Setup
REDIS_HOST = os.getenv("REDIS_HOST", "redis")
redis_client = redis.Redis(host=REDIS_HOST, port=6379, db=0, decode_responses=True)
engine = get_engine()

def get_risk_verdict(score):
    if score < 30: return "LOW (Safe)"
    if score < 60: return "MODERATE (Caution)"
    if score < 80: return "HIGH (Danger)"
    return "CRITICAL (Extreme Risk)"

def calculate_technical_risk(ticker: str):
    """
    Analyzes price action risk using your SIGNAL FILES.
    Instead of raw math, we parse the text alerts from signal_aggregator.
    """
    # 1. Get the text alerts (e.g., ["RSI Overbought", "Volume Spike"])
    signals = get_active_signals(ticker)
    
    # Start neutral
    base_score = 50
    
    # 2. Parse text alerts into a score
    if not signals:
        return 50

    for alert in signals:
        # High Risk keywords
        if "Overbought" in alert: base_score += 15
        if "Oversold" in alert: base_score += 10    # High volatility is still risk
        if "Breakdown" in alert: base_score += 20
        if "Bearish" in alert: base_score += 10
        if "Market Fear" in alert: base_score += 25
        
        # Lower Risk (Bullish) keywords - reduce risk score
        if "Breakout" in alert: base_score -= 10
        if "Golden Cross" in alert: base_score -= 15
        if "Bullish" in alert: base_score -= 5

    return min(100, max(0, base_score))

def calculate_supply_chain_risk(ticker: str):
    """
    Checks the weighted risk of the company's suppliers.
    Risk Contagion: If Supplier fails, Ticker is at risk.
    """
    try:
        # Find verified suppliers
        query = text("""
            SELECT partner_ticker FROM supply_chain 
            WHERE ticker=:t AND relationship='SUPPLIER'
        """)
        with engine.connect() as conn:
            suppliers = conn.execute(query, {"t": ticker}).fetchall()
            
        if not suppliers: return 40 # Unknown supply chain = Moderate uncertainty
        
        total_risk = 0
        count = 0
        
        for sup in suppliers:
            sup_ticker = sup[0]
            # Recursively check the supplier's risk from DB
            r_query = text("SELECT risk_score FROM political_risk WHERE ticker=:s LIMIT 1")
            with engine.connect() as conn:
                res = conn.execute(r_query, {"s": sup_ticker}).fetchone()
            
            if res:
                total_risk += res[0]
                count += 1
                
        if count == 0: return 40
        
        avg_supplier_risk = total_risk / count
        return avg_supplier_risk
        
    except:
        return 40

def get_or_compute_risk_score(ticker: str):
    """
    THE COMPOSITE RISK CALCULATION
    Weights: 40% News, 30% Technicals, 30% Supply Chain
    """
    ticker = ticker.upper()
    cache_key = f"risk_score:{ticker}"

    # 1. Check Cache
    cached = redis_client.get(cache_key)
    if cached: return int(cached)

    # 2. Get Component Scores
    
    # A. News/Headline Risk (From DB, populated by LLM)
    try:
        query = text("SELECT risk_score FROM political_risk WHERE ticker=:t ORDER BY detected_at DESC LIMIT 1")
        with engine.connect() as conn:
            row = conn.execute(query, {"t": ticker}).fetchone()
        news_score = int(row[0]) if row else 50
    except: news_score = 50

    # B. Technical Risk (Now uses Signal Aggregator)
    tech_score = calculate_technical_risk(ticker)

    # C. Supply Chain Risk
    supply_score = calculate_supply_chain_risk(ticker)

    # 3. Weighted Formula
    # News (40%) + Technicals (30%) + Supply Chain (30%)
    final_score = (news_score * 0.4) + (tech_score * 0.3) + (supply_score * 0.3)
    final_score = int(final_score)

    # 4. Save & Return
    redis_client.set(cache_key, final_score, ex=3600) # 1 hour cache
    
    # Debug Logging
    print(f"📊 RISK CALC for {ticker}: News={news_score}, Tech={tech_score}, Supply={supply_score} -> FINAL={final_score}")
    
    return final_score