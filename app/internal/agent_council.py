import os
import pandas as pd
from langchain_ollama import ChatOllama
from langchain_core.messages import SystemMessage, HumanMessage
from sqlalchemy import text
from services.db_manager import get_engine
from services.indicators import calculate_rsi

engine = get_engine()
LLM_MODEL = os.getenv("OLLAMA_MODEL_NAME", "phi3:mini")
LLM_URL = os.getenv("OLLAMA_API_URL", "http://host.docker.internal:11434")

# Temperature 0.1 for high precision/less rambling
llm = ChatOllama(base_url=LLM_URL, model=LLM_MODEL, temperature=0.1)

def sanitize(text):
    """Cleans up AI output artifacts."""
    garbage = ["## Instruction", "Instruction:", "User:", "OUTPUT FORMAT"]
    for g in garbage:
        if g in text: text = text.split(g)[0]
    return text.strip()

# --- 1. ROBUST DATA FETCHING ---
def get_tech_analysis(ticker):
    try:
        # Fetch just enough data for indicators (60 bars)
        query = text(f"SELECT close FROM market_data WHERE ticker=:t ORDER BY timestamp DESC LIMIT 60")
        with engine.connect() as conn:
            df = pd.read_sql(query, conn, params={"t": ticker})
        
        if df.empty: return "No Price Data Available"
        
        # Sort chronological for calculation
        df = df.iloc[::-1] 
        current_price = df['close'].iloc[-1]
        
        # Calculate Indicators safely
        rsi_val = 50.0
        try:
            rsi_series = calculate_rsi(df['close'])
            if not rsi_series.empty:
                rsi_val = rsi_series.iloc[-1]
        except: pass
        
        # Trend Calculation
        trend = "NEUTRAL"
        try:
            sma20 = df['close'].rolling(20).mean().iloc[-1]
            if current_price > sma20: trend = "BULLISH"
            else: trend = "BEARISH"
        except: pass
        
        return f"Price: ${current_price:.2f}, RSI: {rsi_val:.1f}, Trend: {trend}"
    except Exception as e:
        return f"Tech Data Error: {str(e)}"

def get_fund_analysis(ticker):
    try:
        query = text(f"SELECT pe_ratio, debt_to_equity FROM fundamentals WHERE ticker=:t")
        with engine.connect() as conn:
            row = conn.execute(query, {"t": ticker}).fetchone()
        
        if not row: return "Fundamentals N/A"
        
        pe = row[0] if row[0] is not None else 0
        de = row[1] if row[1] is not None else 0
        
        return f"P/E Ratio: {pe}, Debt/Equity: {de}"
    except Exception as e: 
        return f"Fund Data Error: {str(e)}"

def get_risk_analysis(ticker):
    try:
        query = text(f"SELECT risk_score, risk_factor FROM political_risk WHERE ticker=:t ORDER BY detected_at DESC LIMIT 1")
        with engine.connect() as conn:
            row = conn.execute(query, {"t": ticker}).fetchone()
        
        if not row: return "Risk Score: 0/100 (Low Risk)"
        
        return f"Risk Score: {row[0]}/100 (Main Factor: {row[1]})"
    except Exception as e:
        return f"Risk Data Error: {str(e)}"

# --- 2. SINGLE-SHOT COUNCIL ---
def run_council(ticker):
    ticker = ticker.upper()
    print(f"⚖️  Convening Council for {ticker}...")
    
    # Step A: Gather Data (Fail-safe)
    try:
        t_data = get_tech_analysis(ticker)
        f_data = get_fund_analysis(ticker)
        r_data = get_risk_analysis(ticker)
        
        print(f"   Inputs -> Tech: {t_data} | Fund: {f_data} | Risk: {r_data}")
    except Exception as e:
        return f"**DATA ERROR**\nCould not fetch data: {e}"

    # Step B: Construct Prompt
    prompt = f"""
    You are the AI Financial Council for {ticker}.
    
    HARD DATA:
    - Technicals: {t_data}
    - Fundamentals: {f_data}
    - Risk: {r_data}
    
    TASK:
    Synthesize this data into a final investment verdict.
    
    OUTPUT FORMAT (Strictly follow this):
    
    **COUNCIL DECISION: {ticker}**
    
    **VERDICT: [BUY, SELL, or HOLD]**
    
    [Write a 2-3 sentence General Analysis summarizing the conflict between the technicals, fundamentals, and risk. Be professional.]
    
    ---
    *Analyst Notes:*
    📈 **Tech:** [Interpret the RSI and Trend data provided above]
    💰 **Fund:** [Interpret the P/E and Debt data provided above]
    🛡️ **Risk:** [Interpret the Risk Score data provided above]
    """
    
    # Step C: Run AI with Error Handling
    try:
        print("   [Council] Invoking LLM...")
        response = llm.invoke([HumanMessage(content=prompt)])
        print("   [Council] Success.")
        return sanitize(response.content)
        
    except Exception as e:
        print(f"   [CRITICAL ERROR] Council Failed: {e}")
        # This message will now appear in your Dashboard instead of "Council offline"
        return f"**COUNCIL ERROR**\n\nI could not connect to the AI Brain.\n\n**Reason:** {str(e)}\n\n**Fix:** Please check if Ollama is running with `OLLAMA_HOST=0.0.0.0`."