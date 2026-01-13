import os
import json
import requests
import pandas as pd
from sqlalchemy import text
from services.db_manager import get_engine, execute_query
from services.risk_engine import get_or_compute_risk_score, get_risk_verdict

# --- CONFIGURATION ---
BASE_OLLAMA_URL = os.getenv('OLLAMA_API_URL', 'http://host.docker.internal:11434')
if not BASE_OLLAMA_URL.endswith('/api/generate'):
    if BASE_OLLAMA_URL.endswith('/'):
        BASE_OLLAMA_URL += 'api/generate'
    else:
        BASE_OLLAMA_URL += '/api/generate'

LLM_MODEL = os.getenv("OLLAMA_MODEL_NAME", "llama3")
engine = get_engine()

# --- CONTEXT GATHERING ---
def get_tech(ticker: str):
    try:
        query = text("SELECT close FROM market_data WHERE ticker=:t ORDER BY timestamp DESC LIMIT 20")
        with engine.connect() as conn:
            df = pd.read_sql(query, conn, params={"t": ticker})
        if df.empty: return "No Price Data"
        current = df['close'].iloc[0]
        avg_20 = df['close'].mean()
        trend = "BULLISH" if current > avg_20 else "BEARISH"
        return f"Price: ${current:.2f}, Trend: {trend}"
    except Exception as e: return f"Tech Error: {e}"

def get_fund(ticker: str):
    try:
        query = text("SELECT pe_ratio, debt_to_equity FROM fundamentals WHERE ticker=:t")
        with engine.connect() as conn:
            row = conn.execute(query, {"t": ticker}).fetchone()
        if not row: return "Fundamentals N/A"
        return f"P/E: {row[0]}, Debt/Eq: {row[1]}"
    except Exception as e: return f"Fund Error: {e}"

def get_risk(ticker: str):
    try:
        score = get_or_compute_risk_score(ticker)
        verdict = get_risk_verdict(score)
        return f"{score}/100 ({verdict})"
    except Exception as e: return f"Risk Error: {e}"

def get_memory(ticker: str):
    try:
        query = text("SELECT verdict, created_at FROM council_verdicts WHERE ticker=:t ORDER BY created_at DESC LIMIT 1")
        with engine.connect() as conn:
            row = conn.execute(query, {"t": ticker}).fetchone()
        if not row: return "No prior analysis."
        return f"Last Verdict: {row[0]} on {row[1]}"
    except: return "Memory Error"

# --- JSON CLEANING & FORMATTING ---
def clean_and_format_response(text):
    data = None
    try:
        data = json.loads(text)
    except:
        text = text.strip()
        start = text.find('{')
        end = text.rfind('}') + 1
        if start != -1 and end != -1:
            try:
                data = json.loads(text[start:end])
            except: pass
            
    if not data: data = {}

    norm = {k.lower(): v for k, v in data.items()}

    # 1. EXTRACT CORE FIELDS
    verdict = norm.get("verdict", norm.get("decision", "HOLD")).upper()
    if verdict not in ["BUY", "SELL", "HOLD"]: verdict = "HOLD"
    
    horizon = norm.get("horizon", norm.get("time_horizon", "Medium-term"))
    
    conf = norm.get("confidence", 50)
    if conf > 1: conf = conf / 100.0

    analysis = norm.get("analysis", norm.get("reasoning", "Analysis unavailable."))
    bull_case = norm.get("bull_case", "No bull case.")
    bear_case = norm.get("bear_case", "No bear case.")

    # 2. THE FIX: ADD ALL POSSIBLE KEYS
    final_data = {
        # --- FIX FOR VERDICT ---
        "decision": verdict,      
        "verdict": verdict,
        "Verdict": verdict,

        # --- FIX FOR HORIZON (Likely 'time_horizon' or 'timeHorizon') ---
        "horizon": horizon,
        "Horizon": horizon,
        "time_horizon": horizon,
        "timeHorizon": horizon,
        "duration": horizon,

        # --- FIX FOR ANALYSIS (Likely 'reasoning') ---
        "analysis": analysis,
        "Analysis": analysis,
        "reasoning": analysis,
        "rationale": analysis,
        "description": analysis,

        # --- STANDARD FIELDS ---
        "confidence": conf,
        "Confidence": conf,
        "bull_case": bull_case,
        "bear_case": bear_case,
        "bullCase": bull_case,
        "bearCase": bear_case
    }
    return final_data

def save_verdict(ticker, data):
    try:
        execute_query(
            "INSERT INTO council_verdicts (ticker, verdict, confidence, time_horizon, reasoning) VALUES (:t, :v, :c, :h, :r)",
            {"t": ticker, "v": data["verdict"], "c": data["confidence"], "h": data["horizon"], "r": data["analysis"]}
        )
    except Exception as e: print(f"⚠️ Memory Save Failed: {e}")

# --- MAIN EXECUTION ---
def run_council(ticker: str):
    print(f"🐂🐻 Convening Internal Council for {ticker}...")
    
    prompt = f"""
    You are a financial investment council analyzing {ticker}.
    
    [CONTEXT]
    Technicals: {get_tech(ticker)}
    Fundamentals: {get_fund(ticker)}
    Risk: {get_risk(ticker)}
    
    [TASK]
    Debate and provide a trading verdict.
    
    REQUIRED JSON OUTPUT:
    {{
        "bull_case": "...",
        "bear_case": "...",
        "verdict": "BUY", "SELL", or "HOLD",
        "confidence": 85,
        "horizon": "Short-term",
        "analysis": "..."
    }}
    IMPORTANT: Return ONLY the JSON object.
    """

    try:
        payload = {"model": LLM_MODEL, "prompt": prompt, "stream": False, "format": "json"}
        res = requests.post(BASE_OLLAMA_URL, json=payload, timeout=90)
        
        if res.status_code == 200:
            raw_response = res.json().get("response", "")
            final_data = clean_and_format_response(raw_response)
            save_verdict(ticker, final_data)
            return final_data
        else:
            return {"decision": "ERROR", "verdict": "ERROR", "analysis": f"API Error: {res.status_code}"}

    except Exception as e:
        print(f"❌ COUNCIL INTERNAL ERROR: {e}")
        return {"decision": "ERROR", "verdict": "ERROR", "analysis": "Internal Server Error"}