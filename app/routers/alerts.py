"""Alerts & daily brief API (events written by services/event_engine.py)."""
import json
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter
from sqlalchemy import text

from services.db_manager import get_engine
from services.redis_manager import get_redis_client

router = APIRouter()
engine = get_engine()
r = get_redis_client()


def _ensure():
    from services.event_engine import ensure_table
    ensure_table()


@router.get("")
def list_events(ticker: Optional[str] = None, unread_only: bool = False, limit: int = 100):
    _ensure()
    where, params = [], {"n": max(1, min(limit, 500))}
    if ticker:
        where.append("ticker=:t"); params["t"] = ticker.upper()
    if unread_only:
        where.append("read_at IS NULL")
    w = (" WHERE " + " AND ".join(where)) if where else ""
    with engine.connect() as conn:
        rows = conn.execute(text(f"SELECT id, ticker, kind, severity, title, body, evidence_json, event_time, created_at, read_at "
                                 f"FROM oracle_events{w} ORDER BY created_at DESC, id DESC LIMIT :n"), params).mappings().all()
    out = []
    for row in rows:
        d = dict(row)
        try:
            d["evidence"] = json.loads(d.pop("evidence_json") or "{}")
        except Exception:
            d["evidence"] = {}
        for k in ("event_time", "created_at", "read_at"):
            d[k] = str(d[k]) if d[k] else None
        out.append(d)
    return out


@router.get("/unread-count")
def unread_count():
    _ensure()
    with engine.connect() as conn:
        n = conn.execute(text("SELECT COUNT(*) FROM oracle_events WHERE read_at IS NULL")).scalar()
        last = conn.execute(text("SELECT MAX(id) FROM oracle_events")).scalar()
    return {"unread": int(n or 0), "latest_id": int(last or 0)}


@router.post("/{event_id}/read")
def mark_read(event_id: int):
    with engine.begin() as conn:
        conn.execute(text("UPDATE oracle_events SET read_at=NOW() WHERE id=:i AND read_at IS NULL"), {"i": event_id})
    return {"ok": True}


@router.post("/read-all")
def mark_all_read():
    with engine.begin() as conn:
        conn.execute(text("UPDATE oracle_events SET read_at=NOW() WHERE read_at IS NULL"))
    return {"ok": True}


@router.post("/scan")
def scan_now():
    """Run the event checks immediately instead of waiting for the next cycle."""
    from services.event_engine import scan
    return {"events_last_24h": scan()}


@router.get("/brief")
def daily_brief(refresh: bool = False):
    """Morning-style brief for the whole watchlist: facts per company (deterministic) plus one
    short AI summary written only from those facts and number-checked. Cached per day."""
    from app.routers.research import _active_watchlist
    from services import llm
    from services.event_engine import daily_moves
    from services.grounding import unsupported_numbers

    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    key = f"brief:{day}"
    if not refresh:
        hit = r.get(key)
        if hit:
            return json.loads(hit)
    _ensure()
    wl = _active_watchlist()
    moves = daily_moves(wl)
    rows = []
    with engine.connect() as conn:
        for t in wl:
            ev = conn.execute(text("SELECT title, severity FROM oracle_events WHERE ticker=:t AND created_at >= NOW() - INTERVAL 1 DAY "
                                   "ORDER BY FIELD(severity,'high','warn','info'), created_at DESC LIMIT 3"), {"t": t}).fetchall()
            head = conn.execute(text("SELECT headline, url, risk_score FROM news_articles WHERE ticker=:t AND published_at >= NOW() - INTERVAL 1 DAY "
                                     "ORDER BY COALESCE(risk_score,0) DESC LIMIT 1"), {"t": t}).fetchone()
            m = moves.get(t)
            rows.append({
                "ticker": t,
                "change_1d": m[0] if m else None, "close": m[1] if m else None, "as_of": m[2] if m else None,
                "events": [{"title": e[0], "severity": e[1]} for e in ev],
                "top_headline": {"headline": head[0], "url": head[1], "risk": head[2]} if head else None,
            })
    facts = "\n".join(
        f"- {x['ticker']}: 1-day change {x['change_1d'] * 100:+.1f}% (close {x['close']:.2f} on {x['as_of']})" if x["change_1d"] is not None else f"- {x['ticker']}: no price change data"
        for x in rows)
    facts += "\n" + "\n".join(f"- {x['ticker']} event: {e['title']}" for x in rows for e in x["events"])
    facts += "\n" + "\n".join(f"- {x['ticker']} headline: {x['top_headline']['headline']}" for x in rows if x["top_headline"])
    summary, flagged = "", []
    try:
        summary = llm.generate(
            "Write a 4-6 sentence factual brief covering this watchlist: what moved, which SEC filings came in, "
            "upcoming earnings dates and notable headlines. Use ONLY these facts; round numbers sensibly (1.2%, $47.9 billion). "
            "Write for someone who has never invested: short sentences, and explain any finance or filing term in a few words "
            "the first time, e.g. '8-K (a short SEC filing announcing a significant event)'. Never call a move or a company "
            "good, bad, strong, weak or risky. No opinions, recommendations, predictions or advice.\n\nFACTS\n" + facts,
            purpose="other", temperature=0.2, max_tokens=350).strip()
        from services.policy import enforce
        summary, policy_removed = enforce(summary)
        flagged = unsupported_numbers(summary, facts)
        try:
            from app.routers.evals import log_answer
            log_answer("brief", None, "daily brief", None, summary, [], flagged, 0, policy=policy_removed)
        except Exception:
            pass
    except Exception as e:
        summary = f"(AI summary unavailable: {e})"
    out = {"day": day, "generated_at": datetime.now(timezone.utc).isoformat(), "summary": summary,
           "unsupported_numbers": flagged, "rows": rows}
    r.set(key, json.dumps(out, default=str), ex=6 * 3600)
    return out
