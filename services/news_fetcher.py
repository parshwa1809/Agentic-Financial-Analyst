"""
News + risk agent.

Every 5 minutes: pull Google News RSS for the watchlist, keep each headline's real
publish time, then score NEW headlines in batches of 20 per AI call (sentiment −1..+1,
risk 0–100 with a category). Batching keeps the Groq free tier well inside budget.

Bug fixed here: the old code formatted RISK_EXTRACTION_PROMPT without its {ticker}
field, so every call raised KeyError, was swallowed, and every risk score was 0.
"""
import calendar
import os
import sys
import time
from datetime import datetime, timezone

import feedparser
import pandas as pd

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from services import llm
from services.db_manager import get_engine, execute_query
from services.heartbeat import beat
from services.signals.sentiment import analyze_sentiment

engine = get_engine()
SEEN_URLS = set()
BATCH = 20

SCORE_PROMPT = """You score financial news headlines for the stock they are tagged with.

For EACH numbered headline return:
- "sentiment": -1.0 (very negative for the stock) … 0 (neutral) … +1.0 (very positive)
- "risk": 0-100 potential negative price impact. 80-100 war/sanctions/fraud/product ban;
  60-79 lawsuit, big earnings miss, downgrade; 40-59 supply delay, strike, rate fears;
  20-39 competitor launch, mild miss, insider selling; 0-19 product news, dividend hike, partnership, fluff.
- "category": one of Geopolitical, Regulatory, Macro, Company-Specific, None

Return JSON: {{"scores": [{{"i": 0, "sentiment": 0.2, "risk": 15, "category": "Company-Specific"}}]}}

HEADLINES:
{lines}
"""


def _published(entry):
    t = entry.get("published_parsed") or entry.get("updated_parsed")
    if t:
        return datetime.fromtimestamp(calendar.timegm(t), tz=timezone.utc).replace(tzinfo=None)
    return datetime.utcnow()


def _match(title, tickers, names):
    low = f" {title.lower()} "
    out = []
    for sym in tickers:
        name = (names.get(sym) or "").lower()
        if f" {sym.lower()} " in low or f"({sym.lower()})" in low or (name and len(name) > 3 and name in low):
            out.append(sym)
    return out


def score_batch(items):
    """items: [{title, ticker}] → list of (sentiment, risk, category) aligned with items.
    Off by default (NEWS_AI_SCORING=0): AI-assigned sentiment/risk scores aren't sourced facts, so Oracle
    stores headlines with their source and publish time only."""
    if os.getenv("NEWS_AI_SCORING", "0") != "1":
        return [(None, None, None) for _ in items]
    default = [(float(analyze_sentiment(i["title"])), None, None) for i in items]
    lines = "\n".join(f"{n}. [{i['ticker']}] {i['title']}" for n, i in enumerate(items))
    try:
        data = llm.generate_json(SCORE_PROMPT.format(lines=lines), purpose="news", temperature=0, max_tokens=1200)
    except llm.BudgetExceeded as e:
        print(f"⏸️ {e} — using keyword sentiment only")
        return default
    except Exception as e:
        print(f"⚠️ News scoring failed: {e}")
        return default
    out = list(default)
    for s in (data.get("scores") or []) if isinstance(data, dict) else []:
        try:
            n = int(s.get("i"))
            sent = max(-1.0, min(1.0, float(s.get("sentiment", 0))))
            risk = max(0, min(100, int(float(s.get("risk", 0)))))
            out[n] = (sent, risk, str(s.get("category") or "None")[:50])
        except (TypeError, ValueError, IndexError):
            continue
    return out


def _fetch_for(tickers, ticker_names):
    """Collect new headlines for the tickers (30 per RSS query), score them in batches, save."""
    fresh = []
    for i in range(0, len(tickers), 30):
        chunk = tickers[i:i + 30]
        query = "%20OR%20".join(t.replace('/', '-') for t in chunk)
        url = f"https://news.google.com/rss/search?q=({query})%20AND%20(stock%20OR%20market%20OR%20finance)&hl=en-US&gl=US&ceid=US:en"
        for entry in feedparser.parse(url).entries:
            link, title = entry.get("link"), (entry.get("title") or "").strip()
            if not link or not title or link in SEEN_URLS:
                continue
            SEEN_URLS.add(link)
            for t in _match(title, chunk, ticker_names):
                fresh.append({"ticker": t, "title": title, "url": link, "published": _published(entry)})
    if not fresh:
        return 0
    # skip headlines already stored (SEEN_URLS is lost on restart)
    try:
        urls = list({f["url"] for f in fresh})
        have = set()
        with engine.connect() as conn:
            from sqlalchemy import text
            for k in range(0, len(urls), 200):
                part = urls[k:k + 200]
                ph = ",".join(f":u{j}" for j in range(len(part)))
                have |= {r[0] for r in conn.execute(text(f"SELECT url FROM news_articles WHERE url IN ({ph})"),
                                                    {f"u{j}": u for j, u in enumerate(part)})}
        fresh = [f for f in fresh if f["url"] not in have]
    except Exception as e:
        print(f"⚠️ duplicate check failed: {e}")
    saved = 0
    for k in range(0, len(fresh), BATCH):
        batch = fresh[k:k + BATCH]
        for item, (sent, risk, cat) in zip(batch, score_batch(batch)):
            try:
                execute_query(
                    "INSERT IGNORE INTO news_articles (ticker, headline, url, published_at, sentiment_score, risk_score, risk_factor) "
                    "VALUES (:t, :h, :u, :p, :s, :r, :c)",
                    {"t": item["ticker"], "h": item["title"], "u": item["url"], "p": item["published"],
                     "s": sent, "r": risk, "c": cat})
                saved += 1
                if risk is not None and risk > 40:
                    print(f"⚠️ High risk for {item['ticker']}: {cat} ({risk}) — {item['title'][:80]}")
                    execute_query(
                        "INSERT INTO political_risk (ticker, risk_score, risk_factor, headline, detected_at) VALUES (:t, :s, :f, :h, NOW())",
                        {"t": item["ticker"], "s": risk, "f": cat, "h": item["title"]})
            except Exception as e:
                print(f"⚠️ save failed: {e}")
    print(f"📰 {saved} new headlines saved")
    return saved


def fetch_news_for_symbols(symbols):
    """RQ job: fetch news immediately for newly activated tickers."""
    try:
        symbols = [s.upper() for s in symbols]
        df = pd.read_sql("SELECT symbol, name FROM tickers", engine)
        names = {row['symbol']: str(row['name']) for _, row in df.iterrows() if row['symbol'] in symbols}
        _fetch_for(symbols, names)
    except Exception as e:
        print(f"News fetch error for {symbols}: {e}")


def fetch_rss():
    tickers_df = pd.read_sql("SELECT symbol, name FROM tickers WHERE is_active=1", engine)
    if tickers_df.empty:
        return 0
    names = {row['symbol']: str(row['name']) for _, row in tickers_df.iterrows()}
    return _fetch_for(tickers_df['symbol'].tolist(), names)


if __name__ == "__main__":
    print("📰 News + risk agent started (batched AI scoring)...")
    while True:
        try:
            n = fetch_rss()
            beat("news_agent", "ok", f"news cycle complete · {n} new headlines")
        except Exception as e:
            print(f"Global Fetch Error: {e}")
            beat("news_agent", "error", str(e))
        time.sleep(300)
