"""
News relationship agent (LangGraph).

Every minute it takes ALL headlines it hasn't processed yet (not just the newest),
asks the local LLM whether a headline states a supplier / customer / competitor
relationship between two companies, and saves a link only when:
  - both companies resolve to listed US tickers,
  - the quote is really in the headline and names the partner,
  - the relationship type is valid.
Each saved link keeps the article URL as its source.
"""
import json
import os
import time
from typing import List, TypedDict

import pandas as pd
from langgraph.graph import END, StateGraph
from sqlalchemy import text

from services import llm
from services.db_manager import get_engine
from services.heartbeat import beat
from services.redis_manager import get_redis_client
from services.relationship_store import grounded, resolve, save_link

engine = get_engine()
r = get_redis_client()

BATCH = 25          # headlines loaded per cycle
PER_CALL = 15       # headlines sent to the model in one request (saves free-tier quota)
CURSOR_KEY = "agent:last_news_id_num"

PROMPT = """Below are numbered news headlines. For each one that EXPLICITLY says a named company is a
SUPPLIER to, a CUSTOMER of, or a COMPETITOR of another named company, output a relationship.
Most headlines contain none; skip those. Use only what the headline says.

"type" describes target relative to source: SUPPLIER = target supplies source; CUSTOMER = target buys from source.
"quote" = the words from that headline that state the relationship.

Return JSON: {{"relationships": [{{"i": 3, "source": "Apple", "target": "TSMC", "type": "SUPPLIER", "quote": "..."}}]}}

HEADLINES:
{lines}
"""


# Only headlines that could state a relationship are sent to the AI (most can't): saves free-tier quota.
import re as _re
REL_WORDS = _re.compile(r"\b(suppl\w*|suppliers?|customers?|clients?|orders?|contracts?|deals?|agreements?|partner\w*|"
                        r"rivals?|compet\w*|vs\.?|versus|chips? from|sources? from|buy\w* from|sells? to|wins?|signs?|"
                        r"awarded|selects?|chooses|picks|powers|foundry|manufactur\w*|outsourc\w*)\b", _re.I)


class AgentState(TypedDict):
    articles: List[dict]
    saved: int


def load_node(state: AgentState):
    raw = r.get(CURSOR_KEY)
    if raw is None:
        # first run: start with the most recent 200 headlines instead of the whole archive
        with engine.connect() as conn:
            top = conn.execute(text("SELECT COALESCE(MAX(id), 0) FROM news_articles")).scalar() or 0
        raw = str(max(0, int(top) - 200)).encode()
        r.set(CURSOR_KEY, raw)
    last = int(raw.decode())
    df = pd.read_sql(text("SELECT id, ticker, headline, url FROM news_articles WHERE id > :last ORDER BY id ASC LIMIT :n"),
                     engine, params={"last": last, "n": BATCH})
    return {"articles": df.to_dict(orient="records"), "saved": 0}


def extract_and_save_node(state: AgentState):
    arts = state["articles"]
    if not arts:
        return state
    saved = 0
    candidates = [a for a in arts if REL_WORDS.search(str(a.get("headline") or ""))]
    if not candidates:
        r.set(CURSOR_KEY, str(arts[-1]["id"]))
        return {"articles": arts, "saved": 0}
    print(f"   {len(candidates)}/{len(arts)} headlines could state a relationship; sending only those to the AI")
    for k in range(0, len(candidates), PER_CALL):
        chunk = candidates[k:k + PER_CALL]
        lines = "\n".join(f"{i}. [{a.get('ticker')}] {a.get('headline')}" for i, a in enumerate(chunk))
        try:
            data = llm.generate_json(PROMPT.format(lines=lines), purpose="relationships", temperature=0, max_tokens=900)
            rels = data.get("relationships", []) if isinstance(data, dict) else []
        except llm.BudgetExceeded as e:
            print(f"⏸️ {e}")
            return {"articles": arts[:k], "saved": saved}  # leave the rest for tomorrow
        except Exception as e:
            print(f"Extraction error: {e}")
            rels = []
        for rel in rels if isinstance(rels, list) else []:
            if not isinstance(rel, dict):
                continue
            try:
                art = chunk[int(rel.get("i"))]
            except (TypeError, ValueError, IndexError):
                continue
            headline = str(art.get("headline") or "")
            src, tgt = resolve(rel.get("source")), resolve(rel.get("target"))
            if not src or not tgt or src == tgt:
                continue
            if not grounded(rel.get("quote") or headline, headline, must_mention=(rel.get("target"), tgt)):
                continue
            if save_link(src, tgt, rel.get("type"), "news", headline, art.get("url")):
                saved += 1
                print(f"🔗 News link: {src} —{rel.get('type')}→ {tgt}  ({headline[:70]})")
        r.set(CURSOR_KEY, str(chunk[-1]["id"]))
    r.set(CURSOR_KEY, str(arts[-1]["id"]))  # headlines without relationship words are skipped, not re-read
    return {"articles": arts, "saved": saved}


workflow = StateGraph(AgentState)
workflow.add_node("load", load_node)
workflow.add_node("extract_and_save", extract_and_save_node)
workflow.set_entry_point("load")
workflow.add_edge("load", "extract_and_save")
workflow.add_edge("extract_and_save", END)
app = workflow.compile()

if __name__ == "__main__":
    print("🕵️ Relationship Agent Active (LangGraph, evidence-checked)...")
    while True:
        try:
            out = app.invoke({"articles": [], "saved": 0})
            n = len(out.get("articles", []))
            beat("relationship_agent", "ok", f"processed {n} headlines, saved {out.get('saved', 0)} links", ttl=900)
            if n == BATCH:
                continue  # backlog: keep going without sleeping
        except Exception as e:
            print(f"Agent Loop Error: {e}")
            beat("relationship_agent", "error", str(e), ttl=900)
        time.sleep(60)
