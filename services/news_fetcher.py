import os
import sys
import time
import feedparser
import pandas as pd
import json
import requests

# Ensure project root
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from services.db_manager import get_engine, execute_query
from app.internal.prompts import RISK_EXTRACTION_PROMPT

engine = get_engine()
SEEN_URLS = set()

# LLM Config
OLLAMA_URL = os.getenv("OLLAMA_API_URL", "http://host.docker.internal:11434") + "/api/generate"
MODEL = os.getenv("OLLAMA_MODEL_NAME", "phi3:mini")

def analyze_risk_with_llm(headline):
    """Uses Ollama to intelligently score risk."""
    try:
        # Fill the prompt template
        prompt = RISK_EXTRACTION_PROMPT.format(headline=headline)
        
        payload = {
            "model": MODEL,
            "prompt": prompt,
            "stream": False,
            "format": "json"
        }
        
        res = requests.post(OLLAMA_URL, json=payload, timeout=10)
        data = res.json()
        
        # Parse JSON response
        content = data.get("response", "{}")
        risk_data = json.loads(content)
        
        score = risk_data.get("score", 0)
        category = risk_data.get("category", "None")
        
        return score, category
        
    except Exception as e:
        # Fallback to 0 if LLM fails (to keep ingestion fast)
        # print(f"⚠️ Risk LLM Error: {e}") 
        return 0, None

def process_feed_entry(entry, tickers, ticker_names):
    global SEEN_URLS
    link = entry.link
    if link in SEEN_URLS: return
    
    SEEN_URLS.add(link)
    title = entry.title or ''
    lower_title = title.lower()

    # Match Tickers
    matched = []
    for sym in tickers:
        name = ticker_names.get(sym, '').lower()
        if f" {sym.lower()}" in f" {lower_title}" or sym.lower() in lower_title or (name and name in lower_title):
            matched.append(sym)

    if not matched: return

    # 1. Simple Sentiment (Fast)
    # (You can keep your existing sentiment.py import here if desired)
    sentiment_score = 0 
    
    # 2. Advanced Risk Analysis (Slow/Smart)
    risk_score, risk_cat = analyze_risk_with_llm(title)
    
    for t in matched:
        try:
            # Save Article
            execute_query(
                "INSERT IGNORE INTO news_articles (ticker, headline, url, published_at, sentiment_score) VALUES (:t, :h, :u, NOW(), :s)",
                {"t": t, "h": title, "u": link, "s": sentiment_score}
            )
            
            # Save Risk (Only if significant)
            if risk_score > 40:
                print(f"⚠️ High Risk Detected for {t}: {risk_cat} ({risk_score})")
                execute_query(
                    "INSERT INTO political_risk (ticker, risk_score, risk_factor, headline, detected_at) VALUES (:t, :s, :f, :h, NOW())",
                    {"t": t, "s": risk_score, "f": risk_cat, "h": title}
                )
        except: pass

def fetch_rss():
    """Main Loop Function."""
    try:
        tickers_df = pd.read_sql("SELECT symbol, name FROM tickers WHERE is_active=1", engine)
        if tickers_df.empty: return
        
        tickers = tickers_df['symbol'].tolist()
        ticker_names = {row['symbol']: str(row['name']) for _, row in tickers_df.iterrows()}
        
        # Query Construction
        chunk = tickers[:30] 
        clean = [t.replace('/', '-') for t in chunk]
        query = "%20OR%20".join(clean)
        context = "(stock%20OR%20market%20OR%20finance)"
        url = f"https://news.google.com/rss/search?q=({query})%20AND%20{context}&hl=en-US&gl=US&ceid=US:en"

        feed = feedparser.parse(url)
        for entry in feed.entries:
            process_feed_entry(entry, chunk, ticker_names)
            
    except Exception as e:
        print(f"Global Fetch Error: {e}")

if __name__ == "__main__":
    print("📰 Smart News Fetcher Service Started...")
    while True:
        fetch_rss()
        time.sleep(300)