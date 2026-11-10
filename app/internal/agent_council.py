"""Specialist briefing: storage and entry point.

The briefing itself lives in specialists.py (four fact-only analysts + an editor).
This module saves each briefing to `council_verdicts` (table name kept for
compatibility; rows now hold verdict='BRIEFING' and no rating).
"""
import json

from services.db_manager import execute_query


def save_verdict(ticker, data):
    try:
        execute_query(
            "INSERT INTO council_verdicts (ticker, verdict, confidence, time_horizon, reasoning, evidence_json) "
            "VALUES (:t, :v, :c, :h, :r, :e)",
            {"t": ticker, "v": data.get("verdict", "BRIEFING"), "c": 0.0, "h": "", "r": data.get("analysis"),
             "e": json.dumps({k: data.get(k) for k in ("sources", "unsupported_numbers", "model", "agents", "policy_flags", "fingerprint", "rating")},
                             default=str)}
        )
    except Exception as e:
        print(f"⚠️ Briefing save failed: {e}")


def latest_briefing(ticker: str):
    """Most recent stored briefing (rows from the old rating system are ignored)."""
    from sqlalchemy import text
    from services.db_manager import get_engine
    with get_engine().connect() as conn:
        row = conn.execute(text("SELECT reasoning, created_at, evidence_json FROM council_verdicts WHERE ticker=:t "
                                "AND verdict='BRIEFING' ORDER BY created_at DESC LIMIT 1"), {"t": ticker.upper()}).fetchone()
    if not row:
        return None
    ev = json.loads(row[2]) if row[2] else {}
    return {"verdict": "BRIEFING", "decision": "BRIEFING", "analysis": row[0], "created_at": str(row[1]),
            "agents": ev.get("agents") or [], "sources": ev.get("sources") or [], "unsupported_numbers": ev.get("unsupported_numbers") or [],
            "policy_flags": ev.get("policy_flags") or [], "model": ev.get("model"), "fingerprint": ev.get("fingerprint"),
            "rating": ev.get("rating")}


def run_council(ticker: str, force: bool = False):
    """Fact-only specialist briefing (see specialists.py). Skips the AI call when the underlying
    facts and passages are unchanged since the last briefing, unless force=True."""
    from app.internal.specialists import run_specialist_council, _gather, fingerprint
    print(f"📋 Building specialist briefing for {ticker}...")
    try:
        mats = _gather(ticker.upper())
        if not force:
            last = latest_briefing(ticker)
            if last and last.get("fingerprint") == fingerprint(mats):
                print(f"   ⏭️  {ticker}: data unchanged since {last['created_at']}, no AI call")
                return {**last, "unchanged": True}
        data = run_specialist_council(ticker, mats)
    except Exception as e:
        print(f"❌ BRIEFING ERROR: {e}")
        return {"decision": "ERROR", "verdict": "ERROR", "analysis": f"Briefing failed: {e}"}
    save_verdict(ticker.upper(), data)
    return data
