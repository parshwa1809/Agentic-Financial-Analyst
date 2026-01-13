import sys, os, json, requests, time
import yfinance as yf
from services.db_manager import execute_query

# --- IMPORT SEARCH HUB ---
from services.search_engine_hub import search_web_unlimited

# --- CONFIG ---
def get_ollama_url():
    base = os.getenv("OLLAMA_API_URL", "http://host.docker.internal:11434")
    if base.endswith("/"): base = base[:-1]
    if not base.endswith("/api/generate"): base += "/api/generate"
    return base

OLLAMA_URL = get_ollama_url()
MODEL = os.getenv("OLLAMA_MODEL_NAME", "llama3") 

# --- TICKER RESOLUTION MAP ---
TICKER_MAP = {
    "AMAZON": "AMZN", "AMAZON.COM": "AMZN",
    "APPLE": "AAPL",
    "GOOGLE": "GOOGL", "ALPHABET": "GOOGL",
    "MICROSOFT": "MSFT",
    "TESLA": "TSLA",
    "NVIDIA": "NVDA",
    "META": "META", "FACEBOOK": "META",
    "TSMC": "TSM", "TAIWAN SEMICONDUCTOR": "TSM",
    "FOXCONN": "HNHPF",
    "EBAY": "EBAY",
    "INTEL": "INTC",
    "AMD": "AMD",
    "SAMSUNG": "SSNLF"
}

# --- VALIDATION LOGIC ---
BLACKLIST = {"TBA", "TBA1", "TBA2", "ODM", "OEM", "NONE", "NULL", "N/A", "UNKNOWN", "VARIOUS"}

def is_valid_ticker(symbol):
    symbol = symbol.upper().strip()
    if symbol in BLACKLIST: return False
    if len(symbol) > 6 or len(symbol) < 2: return False
    if any(char.isdigit() for char in symbol): return False
    try:
        tik = yf.Ticker(symbol)
        hist = tik.history(period="1d")
        if hist.empty: return False
    except Exception: return False
    return True

def clean_json_string(text):
    text = text.replace("```json", "").replace("```", "").strip()
    start = text.find("{")
    end = text.rfind("}") + 1
    if start != -1 and end != -1: return text[start:end]
    return text

def resolve_ticker(name):
    clean_name = name.upper().strip()
    return TICKER_MAP.get(clean_name, clean_name)

# ==========================================
# 📡 STRATEGIES
# ==========================================
def fetch_strategy_yfinance(ticker):
    print(f"      📡 [Strategy A] Fetching Yahoo Finance for {ticker}...")
    try:
        stock = yf.Ticker(ticker)
        summary = stock.info.get('longBusinessSummary', '')
        if len(summary) < 50: return None
        return f"COMPANY: {ticker}\nSUMMARY: {summary}"
    except: return None

def fetch_strategy_web_search(ticker):
    print(f"      🌍 [Strategy B] Searching Web for {ticker} Supply Chain...")
    query = f"Who are the major suppliers and customers of {ticker} stock? recent reports"
    try:
        return search_web_unlimited(query, max_results=3)
    except Exception as e:
        print(f"      ⚠️ Search failed: {e}")
        return None

def fetch_strategy_internal(ticker):
    print(f"      🧠 [Strategy C] Using Internal LLM Knowledge for {ticker}...")
    return "INTERNAL_KNOWLEDGE_ONLY"

# ==========================================
# ⚙️ EXTRACTION ENGINE
# ==========================================
def get_partners(ticker, context):
    if context == "INTERNAL_KNOWLEDGE_ONLY":
        prompt = f"""
        List 5 major supply chain partners for {ticker}.
        IMPORTANT: Return the STOCK TICKER if possible (e.g. use 'AMZN' instead of 'Amazon').
        Return JSON: {{ "partners": [ {{"partner": "AMZN", "type": "SUPPLIER", "reason": "Cloud Services"}} ] }}
        """
    else:
        prompt = f"""
        Identify supply chain partners for {ticker} from the text below.
        [CONTEXT]: "{context[:2500]}"
        RULES:
        1. If a partner is public, convert to their STOCK TICKER (e.g., 'Amazon' -> 'AMZN').
        2. If private or unknown, use their Short Name.
        3. Return JSON: {{ "partners": [ {{"partner": "TICKER_OR_NAME", "type": "SUPPLIER", "reason": "..."}} ] }}
        """

    try:
        res = requests.post(
            OLLAMA_URL, 
            json={"model": MODEL, "prompt": prompt, "stream": False, "format": "json"}, 
            timeout=120
        )
        if res.status_code != 200: return []
        
        cleaned_text = clean_json_string(res.json().get("response", "{}"))
        data = json.loads(cleaned_text)
        return data.get("partners", [])
    except: return []

def smart_research_pipeline(ticker):
    all_partners = {} 
    
    # --- ATTEMPT 1: Yahoo Finance (Fastest) ---
    context = fetch_strategy_yfinance(ticker)
    if context:
        print(f"      📝 Analyzing Yahoo Finance data for {ticker}...")
        results = get_partners(ticker, context)
        # Filter for VALID tickers only
        valid_count_in_attempt = 0
        for p in results:
            real_ticker = resolve_ticker(p['partner'])
            if is_valid_ticker(real_ticker) and real_ticker != ticker:
                p['partner'] = real_ticker
                all_partners[real_ticker.upper()] = p
                valid_count_in_attempt += 1
        
        if valid_count_in_attempt == 0:
            print(f"      ⚠️ Yahoo produced results, but none were valid tickers. Treating as failure.")

    # --- ATTEMPT 2: Web Search (Fallback) ---
    # Trigger if:
    # 1. Yahoo failed (no context)
    # 2. OR Yahoo worked but yielded 0 VALID partners (len(all_partners) == 0)
    if len(all_partners) == 0:
        print(f"      🌍 [Strategy B] Switching to Web Search (Yahoo failed to yield valid partners)...")
        context = fetch_strategy_web_search(ticker)
        
        if context:
            results = get_partners(ticker, context)
            for p in results: 
                real_ticker = resolve_ticker(p['partner'])
                # We save everything from Web Search, filtering happens in discover_partners
                p['partner'] = real_ticker
                all_partners[real_ticker.upper()] = p

    # --- ATTEMPT 3: Internal Memory (Last Resort) ---
    if len(all_partners) == 0:
        context = fetch_strategy_internal(ticker)
        results = get_partners(ticker, context)
        for p in results: 
            real_ticker = resolve_ticker(p['partner'])
            p['partner'] = real_ticker
            all_partners[real_ticker.upper()] = p

    return list(all_partners.values())

def save_mirrored_relationship(ticker, partner, relationship, reason, confidence=0.85):
    # 1. CRITICAL FIX: Ensure the partner exists in the 'tickers' table FIRST.
    # If we don't do this, the Foreign Key constraint will block the supply_chain insert.
    try:
        execute_query(
            "INSERT IGNORE INTO tickers (symbol, name, is_active) VALUES (:s, :n, 0)", 
            {"s": partner, "n": partner}
        )
    except Exception as e:
        print(f"      ⚠️  Failed to create ticker {partner}: {e}")

    # 2. Save Direct Link (e.g. MSFT -> NVDA)
    try:
        execute_query(
            "INSERT IGNORE INTO supply_chain (ticker, partner_ticker, relationship, confidence, reason) VALUES (:s, :p, :r, :c, :txt)",
            {"s": ticker, "p": partner, "r": relationship, "c": confidence, "txt": reason}
        )
    except Exception as e: 
        print(f"      ❌ Failed to save direct link {ticker}->{partner}: {e}")

    # 3. Save Inverse Link (e.g. NVDA -> MSFT)
    inverse_map = {"SUPPLIER": "CUSTOMER", "CUSTOMER": "SUPPLIER", "PARTNER": "PARTNER", "COMPETITOR": "COMPETITOR"}
    inv_rel = inverse_map.get(relationship, "PARTNER")

    try:
        execute_query(
            "INSERT IGNORE INTO supply_chain (ticker, partner_ticker, relationship, confidence, reason) VALUES (:s, :p, :r, :c, :txt)",
            {"s": partner, "p": ticker, "r": inv_rel, "c": confidence, "txt": f"Inverse: {reason}"}
        )
        return True
    except Exception as e: 
        pass
    
    return False

def discover_partners(ticker):
    """
    Wrapper for API compatibility. 
    Explicitly SAVES data to the DB so the Deep Dive page works.
    """
    print(f"🕵️‍♂️ Deep Dive: Starting supply chain discovery for {ticker}...")
    partners = smart_research_pipeline(ticker)
    
    saved_count = 0
    for p in partners:
        p_tick = p.get("partner", "").upper().strip()
        p_type = p.get('type', 'SUPPLIER').upper()
        
        # VALIDATION CHECK
        if not is_valid_ticker(p_tick):
            continue

        if p_tick != ticker:
            save_mirrored_relationship(ticker, p_tick, p_type, p.get('reason', 'AI Identified'))
            saved_count += 1
            
    print(f"✅ Deep Dive Complete: Saved {saved_count} partners for {ticker}")
    return saved_count

def run_continuous_cycle():
    print(f"♾️   Starting Bidirectional Supply Chain Worker...")
    try:
        execute_query("INSERT IGNORE INTO tickers (symbol, name, is_active) VALUES ('AAPL', 'Apple', 1), ('TSLA', 'Tesla', 1), ('NVDA', 'Nvidia', 1), ('EBAY', 'eBay', 1), ('AMZN', 'Amazon', 1)")
    except: pass

    while True:
        try:
            print("\n🔄  Starting New Research Cycle...")
            # This fetches ALL active tickers to continuously update them
            rows = execute_query("SELECT symbol FROM tickers WHERE is_active=1")
            tickers = [r[0] for r in rows] if rows else ["AAPL", "NVDA", "TSLA", "EBAY", "AMZN"]
            
            for ticker in tickers:
                discover_partners(ticker)
                time.sleep(5)

            print("💤  Cycle Complete. Sleeping for 1 hour...")
            time.sleep(3600)
            
        except KeyboardInterrupt: break
        except Exception as e:
            print(f"⚠️  Worker crashed: {e}. Restarting in 30s...")
            time.sleep(30)

if __name__ == "__main__":
    run_continuous_cycle()