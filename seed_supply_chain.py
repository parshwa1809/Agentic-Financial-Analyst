import sys
import os
import json
import requests
import re
from dotenv import load_dotenv

# Ensure we can find services
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '.')))
from services.db_manager import execute_query, get_engine
import pandas as pd

load_dotenv()

OLLAMA_URL = os.getenv("OLLAMA_API_URL", "http://localhost:11434/api/generate")
MODEL = os.getenv("OLLAMA_MODEL_NAME", "phi3:mini")

def get_active_tickers():
    engine = get_engine()
    try:
        df = pd.read_sql("SELECT symbol FROM tickers WHERE is_active=1 AND symbol NOT LIKE '%/%' AND symbol NOT LIKE '^%'", engine)
        return df['symbol'].tolist()
    except: return []

def clean_json_string(text):
    """Removes markdown code blocks and extra whitespace."""
    text = text.strip()
    # Remove ```json and ``` wrapper if present
    if text.startswith("```"):
        text = re.sub(r"^```json\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    return text

def ask_llm_for_partners(ticker):
    """
    Asks the local LLM to list known suppliers/customers for a ticker.
    """
    prompt = f"""
    Identify 3 major supply chain partners for {ticker} (Public Company).
    Return valid JSON only. No intro text.
    Format:
    {{
        "partners": [
            {{"partner": "TSM", "type": "SUPPLIER"}},
            {{"partner": "MSFT", "type": "CUSTOMER"}}
        ]
    }}
    """
    
    try:
        res = requests.post(OLLAMA_URL, json={"model": MODEL, "prompt": prompt, "stream": False, "format": "json"}, timeout=30)
        response_text = res.json().get("response", "{}")
        
        # Clean and Parse
        cleaned_text = clean_json_string(response_text)
        data = json.loads(cleaned_text)
        
        return data.get("partners", [])
        
    except Exception as e:
        print(f"   ⚠️ LLM Error for {ticker}: {e}")
        return []

def seed_chain():
    print("⛓️ Dynamically Seeding Supply Chain (Powered by Ollama)...")
    
    tickers = get_active_tickers()
    if not tickers:
        print("   ❌ No active stock tickers found. (Crypto/Indices skipped)")
        return

    count = 0
    for ticker in tickers:
        print(f"   🔍 Asking AI about {ticker}...")
        partners = ask_llm_for_partners(ticker)
        
        for p in partners:
            try:
                partner_ticker = p.get("partner", "").upper()
                rel_type = p.get("type", "PARTNER").upper()
                
                # Basic validation: Ticker should be 1-5 chars
                if 1 <= len(partner_ticker) <= 5:
                    execute_query(
                        """INSERT IGNORE INTO supply_chain (ticker, partner_ticker, relationship, confidence) 
                           VALUES (:s, :p, :r, 0.8)""",
                        {"s": ticker, "p": partner_ticker, "r": rel_type}
                    )
                    count += 1
                    print(f"      -> Linked {partner_ticker} ({rel_type})")
            except: pass
            
    print(f"✅ Seeded {count} relationships dynamically.")

if __name__ == "__main__":
    seed_chain()