"""
AI Analyst chat with real RAG.

For each question:
  1. LIVE FACTS from the database (latest price bar with its timestamp, fundamentals,
     evidence-backed supply-chain links).
  2. RETRIEVED SOURCES: the passages most similar to the question from the vector store
     (10-K text, profiles, news, relationship evidence), each numbered [S1], [S2], …
  3. The local LLM answers ONLY from those, citing [S#] / [F] for every claim.
  4. Every number in the answer is checked against the facts and sources; any number
     that appears in neither is returned as `unsupported_numbers` so the UI can flag it.
"""
import os
import re
from typing import Optional

import requests
from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import text

from services import llm, rag
from services.db_manager import get_engine
from services.grounding import unsupported_numbers
from services.policy import enforce
from app.internal.explain import means as explain_means
from services.redis_manager import get_redis_client

router = APIRouter()
engine = get_engine()
redis = get_redis_client()

VALID = re.compile(r"^[A-Z]{1,5}([.-][A-Z]{1,2})?$")


class ChatRequest(BaseModel):
    message: str
    ticker: Optional[str] = None
    session_id: str = "default"


# ----------------------------------------------------------------- live facts (compact)
def live_facts(ticker: str) -> str:
    """Numbered facts, each with its source, kept short to save tokens:
    price, the latest two SEC-reported years and the documented relationships."""
    lines = []
    try:
        from app.routers.research import market_price, _ratios
        from app.internal.statements import verified_statements
        mp = market_price(ticker)
        if mp.get("price"):
            lines.append(f"price ${mp['price']:.2f} ({mp['source']}, {mp['as_of']})")
        st = verified_statements(ticker)
        cur = st.get("currency", "USD")
        b = lambda v: f"{v / 1e9:.2f}B {cur}" if v is not None else "n/a"  # noqa: E731
        for i, y in enumerate(st.get("years", [])[:2]):
            it = y["items"]
            r = _ratios(it, mp.get("price") if i == 0 else None)
            pc = lambda v: f"{v * 100:.1f}%" if v is not None else "n/a"  # noqa: E731
            line = (f"FY{y['fiscal_year_end']} (SEC 10-K): revenue {b(it.get('revenue'))}, net income {b(it.get('net_income'))}, "
                    f"operating income {b(it.get('operating_income'))}, free cash flow {b(it.get('free_cash_flow'))}, "
                    f"total debt {b(it.get('total_debt'))}, equity {b(it.get('equity'))}, diluted EPS {it.get('eps_diluted')}, "
                    f"dividends/share {it.get('dps')}; net margin {pc(r.get('net_margin'))}, ROE {pc(r.get('roe'))}")
            if i == 0 and r.get("pe") is not None:
                line += f", P/E {r['pe']:.1f}x"
            lines.append(line)
    except Exception as e:
        print(f"⚠️ facts unavailable for {ticker}: {e}")
    try:
        from app.routers.market import get_supply_chain
        links = get_supply_chain(ticker, 1, False).get("links", [])[:6]
        lines += [f"relationship: {l['statement']}" for l in links if l.get("statement")]
    except Exception:
        pass
    return "\n".join(f"[F{i + 1}] {x}" for i, x in enumerate(lines)) or "(no stored data for this ticker)"


TEXT_TYPES = {
    "news": re.compile(r"\b(news|headline|latest|recent|today|this week|announce)", re.I),
    "filing": re.compile(r"\b(risk|10-?k|annual report|segment|strategy|business|competition|litigation|legal|employees)\b", re.I),
}
MIN_SIM = 0.45


def _retrieve(question: str, ticker: Optional[str]):
    """5 passages max, deduplicated, filtered by relevance and by the kind of document the question is about."""
    kinds = [k for k, rx in TEXT_TYPES.items() if rx.search(question)]
    doc_types = kinds if len(kinds) == 1 else None
    hits = rag.search(question, ticker=ticker, k=8, doc_types=doc_types)
    out, seen = [], set()
    for h in hits:
        key = (h.get("title"), h["chunk"][:80])
        if h.get("score", 1) < MIN_SIM or key in seen:
            continue
        seen.add(key)
        out.append(h)
        if len(out) == 5:
            break
    return out


def _cache_key(ticker, question, facts):
    import hashlib
    q = re.sub(r"\W+", " ", question.lower()).strip()
    return "chat:v3:" + hashlib.sha1(f"{ticker}|{q}|{facts}".encode()).hexdigest()


# ----------------------------------------------------------------- endpoints
@router.post("/ask")
def chat(request: ChatRequest, _log: bool = True):
    import json
    import time as _t
    _t0 = _t.time()
    ticker = (request.ticker or "").upper().strip() or None
    if ticker and not VALID.match(ticker):
        ticker = None

    # 1) Figures, price and relationships: answered straight from the data, no AI call.
    try:
        from app.internal import fact_answers
        direct = fact_answers.answer(request.message, ticker)
    except Exception as e:
        print(f"⚠️ fact answer failed: {e}")
        direct = None
    if direct:
        if _log:
            from app.routers.evals import log_answer
            log_answer("facts", ticker, request.message, "no AI (SEC data)", direct["response"], direct["sources"], [],
                       (_t.time() - _t0) * 1000)
        return direct

    # 2) Questions that need reading text: compact RAG + one AI call, cached.
    facts = live_facts(ticker) if ticker else "(no ticker selected)"
    ck = _cache_key(ticker, request.message, facts)
    try:
        hit = redis.get(ck)
        if hit:
            return {**json.loads(hit), "cached": True}
    except Exception:
        pass

    sources, indexing = [], False
    try:
        sources = _retrieve(request.message, ticker)
        if ticker and not any(s["ticker"] == ticker for s in sources):
            redis.rpush("rag:queue", ticker)  # nothing indexed for this company yet: index it now
            indexing = True
    except Exception as e:
        print(f"⚠️ RAG search unavailable: {e}")
    if not sources and facts.startswith("(no"):
        return {"response": "I have no stored filings, news or figures for this question yet, so I can't answer it from sources.",
                "sources": [], "unsupported_numbers": [], "policy_removed": [], "indexing": indexing, "model": None, "mode": "none"}

    src_block = "\n\n".join(
        f"[S{i+1}] {s['title']} ({s['doc_type']}{', ' + str(s['published_at'])[:10] if s.get('published_at') else ''})\n{s['chunk'][:700]}"
        for i, s in enumerate(sources)) or "(none)"

    prompt = f"""Answer about {ticker or 'the market'} using ONLY the facts and sources below.

FACTS
{facts}

SOURCES
{src_block}

QUESTION: {request.message}

RULES: cite every claim as [F#] or [S#]; use only numbers that appear in them (rounding is fine); if the answer is not in them, say so in one sentence.
Write for someone who has never invested: start with one or two plain sentences that answer the question, then the details.
The first time you use a finance or filing term, explain it in a few everyday words in brackets, e.g. "10-K (yearly report to the SEC)".
Round numbers ($47.9 billion, 26%). Compare a number with something only if that comparison is in the facts or sources.
Never call a number or the company good, bad, strong, weak, healthy, cheap, expensive or risky.
At most 120 words, short sentences or short bullets, no tables. Quote at most 20 words from a source.
No recommendations, ratings, price targets, predictions or opinions."""
    try:
        answer = llm.generate(prompt, purpose="chat", temperature=0.1, max_tokens=350).strip()
    except llm.BudgetExceeded as e:
        return {"response": f"Today's free AI quota for chat is used up ({e}). Questions about reported figures, price and relationships still work without AI.",
                "sources": [], "unsupported_numbers": [], "policy_removed": [], "model": llm.model_name(), "mode": "none"}
    except Exception as e:
        print(f"❌ CHAT ERROR: {e}")
        return {"response": f"I couldn't reach the AI model ({llm.model_name()}): {e}", "sources": [], "unsupported_numbers": [],
                "policy_removed": [], "model": llm.model_name(), "mode": "none"}

    answer, policy_removed = enforce(answer)  # facts-only rule, checked in code
    n_f, n_s = facts.count("[F"), len(sources)
    # drop citations that point at nothing
    answer = re.sub(r"\[(F|S)(\d+)\]", lambda m: m.group(0) if int(m.group(2)) <= (n_f if m.group(1) == "F" else n_s) else "", answer)
    cited = {int(n) for n in re.findall(r"\[S(\d+)\]", answer)}
    uncited = not re.search(r"\[(F|S)\d+\]", answer)
    flagged = unsupported_numbers(answer, facts + "\n" + src_block)
    if _log:
        from app.routers.evals import log_answer
        log_answer("chat", ticker, request.message, llm.model_name(), answer, sources, flagged, (_t.time() - _t0) * 1000,
                   policy=policy_removed)
    out = {
        "response": answer + ("\n\n(No source was cited for this answer, so treat it with care.)" if uncited else "")
                    + "\n\n" + explain_means("text"),
        "sources": [{"id": f"S{i+1}", "title": s["title"], "doc_type": s["doc_type"], "url": s.get("source_url"),
                     "published_at": str(s.get("published_at") or "") or None, "score": s["score"], "cited": (i + 1) in cited,
                     "snippet": s["chunk"][:280]} for i, s in enumerate(sources)],
        "unsupported_numbers": flagged,
        "policy_removed": policy_removed,
        "indexing": indexing,
        "model": llm.model_name(),
        "mode": "ai",
    }
    if not indexing:
        try:
            redis.set(ck, json.dumps(out, default=str), ex=6 * 3600)
        except Exception:
            pass
    return out


@router.get("/llm-usage")
def llm_usage():
    """Today's AI request usage against the free-tier budgets."""
    return llm.usage()


@router.get("/search")
def search(q: str, ticker: Optional[str] = None, k: int = 8):
    """Raw retrieval, handy for checking what the analyst will see."""
    return {"results": rag.search(q, ticker=ticker, k=min(max(k, 1), 25))}


@router.get("/rag-stats")
def rag_stats(ticker: Optional[str] = None):
    return rag.stats(ticker)


@router.post("/index/{ticker}")
def index_now(ticker: str):
    t = ticker.upper()
    if not VALID.match(t):
        return {"queued": False, "error": "invalid ticker"}
    redis.rpush("rag:queue", t)
    return {"queued": True, "ticker": t}
