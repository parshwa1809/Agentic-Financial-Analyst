"""
Background indexer for the RAG store.

Every cycle it embeds anything new:
  - each watchlist company's latest 10-K / 20-F (whole document, chunked)
  - each watchlist company's business profile
  - verified relationship evidence quotes (with their source links)
  - every news headline not yet indexed
It also serves on-demand requests: the chat pushes a ticker onto the Redis list
`rag:queue` when asked about a company that has no documents yet, and it is
indexed within seconds.
"""
import os
import sys
import time

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import pandas as pd
import yfinance as yf
from sqlalchemy import text

from services import rag
from services.db_manager import get_engine
from services.heartbeat import beat
from services.redis_manager import get_redis_client
from services.sec_filings import relationship_passages

engine = get_engine()
r = get_redis_client()
CYCLE_SECONDS = int(os.getenv("RAG_CYCLE_SECONDS", "900"))
MAX_FILING_CHUNKS = int(os.getenv("RAG_MAX_FILING_CHUNKS", "600"))
NEWS_CURSOR = "rag:last_news_id"


def index_ticker(ticker: str) -> int:
    ticker = ticker.upper()
    docs = []
    filing = relationship_passages(ticker)
    if filing and filing.get("full_text"):
        title = f"{ticker} {filing['form']} (filed {filing['filed']})"
        for c in rag.chunk_text(filing["full_text"])[:MAX_FILING_CHUNKS]:
            docs.append({"ticker": ticker, "doc_type": "filing", "title": title, "source_url": filing["url"],
                         "published_at": filing["filed"], "chunk": c})
    try:
        info = yf.Ticker(ticker).info or {}
        summary = info.get("longBusinessSummary")
        if summary:
            docs.append({"ticker": ticker, "doc_type": "profile", "title": f"{info.get('longName', ticker)} — business profile",
                         "source_url": f"https://finance.yahoo.com/quote/{ticker}/profile", "published_at": None, "chunk": summary})
    except Exception as e:
        print(f"   ⚠️ profile for {ticker} failed: {e}")
    try:
        rel = pd.read_sql(text("SELECT partner_ticker, relationship, evidence, source_url, source_type, last_verified "
                               "FROM supply_chain WHERE ticker=:t AND status='active' AND evidence IS NOT NULL "
                               "AND source_type <> 'legacy'"), engine, params={"t": ticker})
        for _, row in rel.iterrows():
            docs.append({"ticker": ticker, "doc_type": "relationship",
                         "title": f"{ticker} → {row['partner_ticker']} ({row['relationship']}, from {row['source_type']})",
                         "source_url": row["source_url"], "published_at": row["last_verified"],
                         "chunk": f"{row['partner_ticker']} is a {str(row['relationship']).lower()} of {ticker}. Evidence: {row['evidence']}"})
    except Exception as e:
        print(f"   ⚠️ relationship evidence for {ticker} failed: {e}")
    n = rag.add_documents(docs)
    print(f"   🧠 {ticker}: {n} new chunks indexed ({len(docs)} candidates)")
    return n


def index_news(limit: int = 500) -> int:
    last = int((r.get(NEWS_CURSOR) or b"0").decode())
    df = pd.read_sql(text("SELECT id, ticker, headline, url, published_at FROM news_articles WHERE id > :l ORDER BY id LIMIT :n"),
                     engine, params={"l": last, "n": limit})
    if df.empty:
        return 0
    docs = [{"ticker": (row["ticker"] or "MARKET").upper(), "doc_type": "news", "title": row["headline"][:500],
             "source_url": row["url"], "published_at": row["published_at"], "chunk": row["headline"]} for _, row in df.iterrows()]
    n = rag.add_documents(docs)
    r.set(NEWS_CURSOR, str(int(df["id"].max())))
    print(f"   📰 {n} new headlines indexed")
    return n


def active_tickers():
    try:
        return [row[0] for row in engine.connect().execute(text("SELECT symbol FROM tickers WHERE is_active=1")).fetchall()]
    except Exception:
        return []


def run():
    print("🧠 RAG indexer started (Ollama embeddings → TiDB)")
    rag.ensure_table()
    next_full = 0
    while True:
        try:
            # on-demand requests from the chat / API, handled within seconds
            while True:
                raw = r.lpop("rag:queue")
                if not raw:
                    break
                index_ticker(raw.decode())
            if time.time() >= next_full:
                total = sum(index_ticker(t) for t in active_tickers()) + index_news()
                s = rag.stats()
                beat("rag_indexer", "ok", f"{s['total']} chunks · +{total} this cycle · {s['vector_search']}", ttl=CYCLE_SECONDS * 3)
                next_full = time.time() + CYCLE_SECONDS
        except Exception as e:
            print(f"❌ RAG indexer error: {e}")
            beat("rag_indexer", "error", f"{e} — is `ollama pull {rag.EMBED_MODEL}` done?", ttl=CYCLE_SECONDS * 3)
            time.sleep(60)
        time.sleep(10)


if __name__ == "__main__":
    time.sleep(15)  # let the API run DB migrations first
    run()
