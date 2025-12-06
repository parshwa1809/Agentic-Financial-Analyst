import os
import sys

# --- FIX: Add Project Root to Path ---
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
# -------------------------------------

import time
import feedparser
import random
import pandas as pd
from services.db_manager import get_engine, execute_query
from services.signals.sentiment import analyze_sentiment

engine = get_engine()

# --- MEMORY CACHE ---
# This ensures we don't alert twice for the same link as long as the service is running
SEEN_URLS = set()

# --- RISK CONFIGURATION ---
RISK_MAP = {
    "Geopolitical": {"words": ["war", "sanctions", "conflict", "invasion", "china", "taiwan", "russia"], "score": 90},
    "Regulatory":   {"words": ["antitrust", "sec", "doj", "lawsuit", "ban", "fine", "crackdown"], "score": 65},
    "Supply":       {"words": ["shortage", "delay", "strike", "supplier", "outage", "supply chain"], "score": 50},
    "Volatility":   {"words": ["crash", "plunge", "collapse", "crisis", "panic", "recession"], "score": 75}
}

def analyze_risk(text):
    text = text.lower()
    for cat, data in RISK_MAP.items():
        for w in data["words"]:
            if w in text:
                variance = random.randint(-2, 2)
                return data["score"] + variance, cat
    return 0, None

def load_processed_urls():
    """Load recent history from DB into Memory on startup."""
    global SEEN_URLS
    print("📥 Loading recent news history into cache...")
    try:
        df = pd.read_sql("SELECT url FROM news_articles WHERE published_at > NOW() - INTERVAL 7 DAY", engine)
        if not df.empty:
            SEEN_URLS = set(df['url'].tolist())
        print(f"✅ Loaded {len(SEEN_URLS)} processed articles.")
    except Exception as e:
        print(f"⚠️ Cache Load Warning: {e}")

def fetch_rss():
    try:
        tickers_df = pd.read_sql("SELECT symbol, name FROM tickers WHERE is_active=1", engine)
    except: return

    if tickers_df.empty: return

    # Build search query
    tickers = tickers_df['symbol'].tolist()
    clean = [t.replace('/', '-') for t in tickers]
    query = "%20OR%20".join(clean)
    context = "(stock%20OR%20market%20OR%20finance%20OR%20crypto%20OR%20earnings)"
    url = f"https://news.google.com/rss/search?q=({query})%20AND%20{context}&hl=en-US&gl=US&ceid=US:en"

    feed = feedparser.parse(url)
    try:
        ticker_names = {row['symbol']: str(row['name']).lower() for _, row in tickers_df.iterrows()}
    except: ticker_names = {}

    new_count = 0
    for entry in feed.entries:
        try:
            link = entry.link
            
            # --- DEDUPLICATION CHECK ---
            if link in SEEN_URLS:
                continue
            
            # Add to memory immediately so we don't process it again next loop
            SEEN_URLS.add(link)
            new_count += 1
            # ---------------------------

            title = entry.title or ''
            lower_title = title.lower()

            matched = []
            for sym, name in ticker_names.items():
                if f" {sym.lower()}" in f" {lower_title}" or sym.lower() in lower_title or (name and name in lower_title):
                    matched.append(sym)

            score = analyze_sentiment(title)
            targets = matched if matched else ["MARKET"]
            
            for t in targets:
                # Insert Article
                try:
                    execute_query(
                        "INSERT IGNORE INTO news_articles (ticker, headline, url, published_at, sentiment_score) VALUES (:t, :h, :u, NOW(), :s)",
                        {"t": t, "h": title, "u": link, "s": score}
                    )
                except: pass

                # Generate Alert
                if abs(score) >= 1:
                    msg = f"{'Positive' if score > 0 else 'Negative'} News: {title[:120]}"
                    try:
                        execute_query("INSERT INTO active_alerts (ticker, message, created_at) VALUES (:t, :m, NOW())", {"t": t, "m": msg})
                    except: pass

                # Analyze Risk
                r_score, r_cat = analyze_risk(title)
                if r_score > 0:
                    try:
                        execute_query(
                            "INSERT INTO political_risk (ticker, risk_score, risk_factor, headline, detected_at) VALUES (:t, :s, :f, :h, NOW())",
                            {"t": t, "s": r_score, "f": r_cat, "h": title}
                        )
                    except: pass
        except Exception: pass
    
    if new_count > 0:
        print(f"📰 Processed {new_count} new articles.")

if __name__ == "__main__":
    print("📰 News Fetcher Service Started...")
    
    # 1. Load history once
    load_processed_urls()
    
    # 2. Loop forever
    while True:
        fetch_rss()
        time.sleep(300) # Wait 5 minutes