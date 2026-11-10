"""Real status of each background agent, for the sidebar and the LIVE badge."""
import os
import time
from datetime import datetime, time as dtime, timezone
from zoneinfo import ZoneInfo

from fastapi import APIRouter
from sqlalchemy import text

from services.db_manager import get_engine
from services.heartbeat import read as read_beat

router = APIRouter()
engine = get_engine()
NY = ZoneInfo("America/New_York")


# NYSE full-day closures (published exchange calendar). Extend each year.
NYSE_HOLIDAYS = {
    "2025-01-01", "2025-01-09", "2025-01-20", "2025-02-17", "2025-04-18", "2025-05-26", "2025-06-19", "2025-07-04",
    "2025-09-01", "2025-11-27", "2025-12-25",
    "2026-01-01", "2026-01-19", "2026-02-16", "2026-04-03", "2026-05-25", "2026-06-19", "2026-07-03", "2026-09-07",
    "2026-11-26", "2026-12-25",
    "2027-01-01", "2027-01-18", "2027-02-15", "2027-03-26", "2027-05-31", "2027-06-18", "2027-07-05", "2027-09-06",
    "2027-11-25", "2027-12-24",
}
# Early closes at 13:00 ET
NYSE_HALF_DAYS = {"2025-07-03", "2025-11-28", "2025-12-24", "2026-11-27", "2026-12-24", "2027-11-26"}


def market_session(now_utc: datetime = None) -> dict:
    """Regular NYSE session Mon–Fri 9:30–16:00 ET, with exchange holidays and early closes."""
    now = (now_utc or datetime.now(timezone.utc)).astimezone(NY)
    day = now.strftime("%Y-%m-%d")
    close = dtime(13, 0) if day in NYSE_HALF_DAYS else dtime(16, 0)
    holiday = day in NYSE_HOLIDAYS
    is_open = now.weekday() < 5 and not holiday and dtime(9, 30) <= now.time() < close
    note = "NYSE holiday" if holiday else ("early close 1:00 PM ET" if day in NYSE_HALF_DAYS else "regular hours 9:30–16:00 ET")
    return {"open": is_open, "now_et": now.strftime("%a %Y-%m-%d %H:%M ET"), "note": note}


def _scalar(sql: str, params=None):
    try:
        with engine.connect() as conn:
            return conn.execute(text(sql), params or {}).scalar()
    except Exception:
        return None


def _age_minutes(ts) -> float:
    if ts is None:
        return None
    if isinstance(ts, str):
        ts = datetime.fromisoformat(ts)
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - ts).total_seconds() / 60.0


def _beat(name: str):
    b = read_beat(name)
    if b:
        b["age_minutes"] = (time.time() - b["ts"]) / 60.0
    return b


@router.get("/status")
def status(ticker: str = None):
    session = market_session()
    agents = []

    # 1. Price stream — judged by the newest bar actually stored, not by "is the process up".
    last_bar = _scalar("SELECT MAX(timestamp) FROM market_data" + (" WHERE ticker=:t" if ticker else ""),
                       {"t": ticker.upper()} if ticker else None)
    age = _age_minutes(last_bar)
    sub = _beat("price_stream_subscription")
    crash = _beat("price_stream")
    if session["open"]:
        if age is not None and age <= 10:
            st, detail = "ok", f"bars arriving · last {age:.0f} min ago"
        else:
            st = "error"
            detail = (f"market open but newest bar is {age/60/24:.0f} days old — check `docker compose logs ingestion-price`"
                      if age is not None else "no bars stored yet")
    else:
        st = "idle"
        detail = f"market closed · last bar {last_bar} UTC" if last_bar else "market closed · no bars stored yet"
    if crash and crash.get("status") == "error" and crash["age_minutes"] < 30:
        st, detail = "error", crash.get("detail", "stream error")
    agents.append({"key": "price", "label": "Price stream", "status": st, "detail": detail,
                   "subscription": sub.get("detail") if sub else None, "last_bar_utc": str(last_bar) if last_bar else None})

    # 2. News agent
    b = _beat("news_agent")
    last_news = _scalar("SELECT MAX(published_at) FROM news_articles")
    if b:
        st = "error" if b["status"] == "error" else ("ok" if b["age_minutes"] < 20 else "stale")
        detail = b.get("detail") if b["status"] == "error" else f"last cycle {b['age_minutes']:.0f} min ago"
    else:
        st, detail = "unknown", f"no heartbeat yet · newest headline {last_news}" if last_news else "no heartbeat yet"
    agents.append({"key": "news", "label": "News feed", "status": st, "detail": detail})

    # 3. Supply-chain agent
    b = _beat("supply_chain_agent")
    n_links = _scalar("SELECT COUNT(*) FROM supply_chain")
    n_verified = _scalar("SELECT COUNT(*) FROM supply_chain WHERE status='active' AND source_type <> 'legacy'")
    if b:
        cycle_min = float(os.getenv("RESEARCH_CYCLE_HOURS", "24" if os.getenv("LLM_PROVIDER", "ollama") != "ollama" else "1")) * 60
        st = "error" if b["status"] == "error" else ("ok" if b["age_minutes"] < cycle_min * 2 + 30 else "stale")
        detail = b.get("detail") if b["status"] == "error" else f"{n_verified or 0} evidence-backed / {n_links or 0} links · cycle {b['age_minutes']:.0f} min ago"
    else:
        st, detail = "unknown", f"{n_links or 0} links stored · no heartbeat yet"
    agents.append({"key": "supply", "label": "Supply-chain agent", "status": st, "detail": detail})

    # 4. Agent council
    b = _beat("council")
    last_v = _scalar("SELECT MAX(created_at) FROM council_verdicts")
    if b:
        st = "error" if b["status"] == "error" else ("ok" if b["age_minutes"] < 30 else "stale")
        detail = b.get("detail") if b["status"] == "error" else f"last cycle {b['age_minutes']:.0f} min ago"
    else:
        st, detail = "unknown", f"no heartbeat yet · last briefing {last_v}" if last_v else "no heartbeat yet"
    agents.append({"key": "council", "label": "Specialist briefings", "status": st, "detail": detail})

    # 5. RAG indexer
    b = _beat("rag_indexer")
    if b:
        st = "error" if b["status"] == "error" else ("ok" if b["age_minutes"] < 60 else "stale")
        detail = b.get("detail", "")
    else:
        st, detail = "unknown", "no heartbeat yet"
    agents.append({"key": "rag", "label": "RAG indexer", "status": st, "detail": detail})

    # 6. Event engine
    b = _beat("event_engine")
    if b:
        st = "error" if b["status"] == "error" else ("ok" if b["age_minutes"] < 40 else "stale")
        detail = b.get("detail", "")
    else:
        st, detail = "unknown", "no heartbeat yet"
    agents.append({"key": "events", "label": "Event engine", "status": st, "detail": detail})

    # 7. AI model + free-tier usage
    try:
        from services import llm
        u = llm.usage()
        if llm.metered():
            pct = u["total"]["used"] / max(u["total"]["cap"], 1)
            st = "error" if pct >= 1 else ("stale" if pct >= 0.8 else "ok")
            detail = f"{u['model']} · {u['total']['used']}/{u['total']['cap']} requests today"
        else:
            st, detail = "ok", f"{u['model']} · local, unlimited"
        agents.append({"key": "llm", "label": "AI model", "status": st, "detail": detail})
    except Exception as e:
        agents.append({"key": "llm", "label": "AI model", "status": "unknown", "detail": str(e)[:80]})

    return {"market": session, "agents": agents, "checked_at": datetime.now(timezone.utc).isoformat()}


@router.get("/resolve")
def resolve_names(names: str):
    """Diagnostics: how company names map to listed tickers (comma-separated)."""
    from services.relationship_store import resolve, is_listed
    out = {}
    for n in [x.strip() for x in names.split(",") if x.strip()][:30]:
        t = resolve(n)
        out[n] = {"ticker": t, "listed": bool(t and is_listed(t))}
    return out
