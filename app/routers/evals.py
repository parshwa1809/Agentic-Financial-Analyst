"""
AI quality (evals) — measures how grounded Oracle's AI output is.

Live metrics: every chat answer / council session is logged with its citations, the numbers the
grounding check could not find in the sources, model and latency (`ai_answer_log`).
Benchmark: a fixed set of questions (evals/golden.json) is run against the AI Analyst; questions
with a known answer are scored against the value Oracle computes from the filings.
Relationship funnel: how many relationships the agents proposed vs how many passed the
ticker and quote checks.
"""
import json
import os
import re
import time
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException
from sqlalchemy import text

from services.db_manager import get_engine
from services.redis_manager import get_redis_client

router = APIRouter()
engine = get_engine()
r = get_redis_client()
GOLDEN = os.path.join(os.path.dirname(__file__), "..", "..", "evals", "golden.json")

DDL = [
    """CREATE TABLE IF NOT EXISTS ai_answer_log (
        id BIGINT AUTO_INCREMENT PRIMARY KEY, kind VARCHAR(16), ticker VARCHAR(20), question TEXT, model VARCHAR(80),
        n_sources INT, n_cited INT, citations INT, unsupported INT, unsupported_json TEXT, latency_ms INT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP, INDEX idx_ai_log_time (created_at))""",
    """CREATE TABLE IF NOT EXISTS eval_runs (
        id BIGINT AUTO_INCREMENT PRIMARY KEY, ticker VARCHAR(20), model VARCHAR(80), summary_json TEXT, results_json LONGTEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP)""",
]
_READY = {"ok": False}


def ensure():
    if _READY["ok"]:
        return
    with engine.begin() as conn:
        for d in DDL:
            conn.execute(text(d))
        cols = {r[0].lower() for r in conn.execute(text(
            "SELECT COLUMN_NAME FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'ai_answer_log'")).fetchall()}
        if "policy_flags" not in cols:
            conn.execute(text("ALTER TABLE ai_answer_log ADD COLUMN policy_flags INT DEFAULT 0"))
        if "policy_json" not in cols:
            conn.execute(text("ALTER TABLE ai_answer_log ADD COLUMN policy_json TEXT"))
    _READY["ok"] = True


def log_answer(kind, ticker, question, model, answer, sources, unsupported, latency_ms, policy=None):
    """Called by the chat and council after every AI answer. Never raises."""
    try:
        ensure()
        cited = {int(n) for n in re.findall(r"\[S(\d+)\]", answer or "")}
        citations = len(re.findall(r"\[(?:S\d+|F\d*)\]", answer or ""))
        with engine.begin() as conn:
            conn.execute(text("INSERT INTO ai_answer_log (kind, ticker, question, model, n_sources, n_cited, citations, unsupported, "
                              "unsupported_json, latency_ms, policy_flags, policy_json) VALUES (:k,:t,:q,:m,:ns,:nc,:c,:u,:uj,:l,:pf,:pj)"),
                         {"k": kind, "t": ticker, "q": (question or "")[:2000], "m": model, "ns": len(sources or []), "nc": len(cited),
                          "c": citations, "u": len(unsupported or []), "uj": json.dumps(unsupported or []), "l": int(latency_ms),
                          "pf": len(policy or []), "pj": json.dumps(policy or [])[:8000]})
    except Exception as e:
        print(f"⚠️ eval log failed: {e}")


@router.get("/summary")
def summary(days: int = 7):
    ensure()
    with engine.connect() as conn:
        rows = conn.execute(text("SELECT kind, citations, n_cited, n_sources, unsupported, latency_ms, COALESCE(policy_flags,0) FROM ai_answer_log "
                                 "WHERE created_at >= NOW() - INTERVAL :d DAY"), {"d": days}).fetchall()
        policy_recent = conn.execute(text("SELECT kind, ticker, policy_json, created_at FROM ai_answer_log WHERE policy_flags > 0 "
                                          "ORDER BY id DESC LIMIT 10")).fetchall()
        daily = conn.execute(text("SELECT DATE(created_at) d, COUNT(*), SUM(citations > 0), SUM(unsupported = 0), AVG(latency_ms) "
                                  "FROM ai_answer_log WHERE created_at >= NOW() - INTERVAL 14 DAY GROUP BY DATE(created_at) ORDER BY d")).fetchall()
        last_run = conn.execute(text("SELECT id, ticker, model, summary_json, created_at FROM eval_runs ORDER BY id DESC LIMIT 1")).fetchone()
        links = conn.execute(text("SELECT COALESCE(source_type,'legacy'), status, COUNT(*) FROM supply_chain GROUP BY 1, 2")).fetchall()
    n = len(rows)
    lat = sorted(x[5] for x in rows if x[5] is not None)
    pick = lambda q: lat[min(len(lat) - 1, int(q * len(lat)))] if lat else None  # noqa: E731
    funnel = {k: int(r.get(f"rel:{k}") or 0) for k in ("proposed", "saved", "ungrounded", "unlisted", "bad_type")}
    from services import llm
    return {
        "window_days": days, "answers": n,
        "citation_rate": (sum(1 for x in rows if x[1] > 0) / n) if n else None,
        "clean_number_rate": (sum(1 for x in rows if x[4] == 0) / n) if n else None,
        "avg_unsupported": (sum(x[4] for x in rows) / n) if n else None,
        "policy_clean_rate": (sum(1 for x in rows if x[6] == 0) / n) if n else None,
        "policy_removed_total": sum(x[6] for x in rows),
        "policy_recent": [{"kind": k, "ticker": t, "removed": json.loads(pj or "[]"), "at": str(at)} for k, t, pj, at in policy_recent],
        "source_use_rate": (sum(x[2] for x in rows) / max(1, sum(x[3] for x in rows))) if n else None,
        "latency_ms": {"p50": pick(0.5), "p95": pick(0.95)},
        "by_kind": {k: sum(1 for x in rows if x[0] == k) for k in sorted({x[0] for x in rows})},
        "daily": [{"day": str(d), "answers": int(c), "cited": int(ci or 0), "clean": int(cl or 0), "avg_latency_ms": float(al or 0)} for d, c, ci, cl, al in daily],
        "relationship_funnel": funnel,
        "relationship_rejected": [json.loads(x) for x in (r.lrange("rel:rejected", 0, 9) or [])],
        "relationships_by_source": [{"source": s, "status": st, "count": int(c)} for s, st, c in links],
        "last_run": {"id": last_run[0], "ticker": last_run[1], "model": last_run[2], "summary": json.loads(last_run[3]), "at": str(last_run[4])} if last_run else None,
        "llm_usage": llm.usage(),
    }


@router.get("/runs/{run_id}")
def get_run(run_id: int):
    ensure()
    with engine.connect() as conn:
        row = conn.execute(text("SELECT id, ticker, model, summary_json, results_json, created_at FROM eval_runs WHERE id=:i"), {"i": run_id}).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Run not found")
    return {"id": row[0], "ticker": row[1], "model": row[2], "summary": json.loads(row[3]), "results": json.loads(row[4]), "at": str(row[5])}


def _expected(fact: str, report: dict):
    y = report["years"][0]
    return {
        "revenue": (y["items"].get("revenue"), "$"), "net_income": (y["items"].get("net_income"), "$"),
        "net_margin": (y["ratios"].get("net_margin"), "%"), "dividend_yield": (y["ratios"].get("dividend_yield"), "%"),
        "debt_to_equity": (y["ratios"].get("debt_to_equity"), "x"), "pe": (y["ratios"].get("pe"), "x"),
    }.get(fact, (None, None))


def _found(answer: str, value: float, unit: str) -> bool:
    from services.grounding import NUM, _value
    for m in NUM.finditer(answer or ""):
        tok = m.group(0)
        v, dec, mult = _value(tok)
        if v is None:
            continue
        cand = [v * mult, v]
        if unit == "%":
            cand = [v / 100] if "%" in tok or "percent" in tok.lower() else [v / 100, v]
        tol = abs(value) * 0.02 + (0.0015 if unit == "%" else 0)
        if any(abs(c - value) <= tol for c in cand):
            return True
    return False


@router.post("/run")
def run_benchmark(ticker: str = "AAPL", limit: int = 10):
    """Run the golden questions through the AI Analyst for one company and score them.
    Costs one AI request per question (counted against the chat budget)."""
    ensure()
    from app.routers.chat import ChatRequest, chat
    from app.routers.research import company_report, _norm
    t = _norm(ticker)
    with open(GOLDEN) as f:
        golden = json.load(f)[: max(1, min(limit, 25))]
    report = company_report(t)
    results = []
    for g in golden:
        q = g["question"].replace("{ticker}", t).replace("{name}", report["profile"].get("name") or t)
        t0 = time.time()
        res = chat(ChatRequest(message=q, ticker=t), _log=False)
        ms = int((time.time() - t0) * 1000)
        ans = res.get("response", "")
        exp, unit = _expected(g.get("fact"), report) if g.get("fact") else (None, None)
        item = {"id": g["id"], "category": g["category"], "question": q, "answer": ans[:1500],
                "citations": len(re.findall(r"\[(?:S\d+|F\d*)\]", ans)), "unsupported": res.get("unsupported_numbers", []),
                "n_sources": len(res.get("sources", [])), "latency_ms": ms}
        if exp is not None:
            item["expected"] = exp
            item["correct"] = _found(ans, exp, unit)
        if g.get("expect_refusal"):
            item["correct"] = bool(re.search(r"(not (in|found|available|contain)|don't have|do not have|cannot|can't|no (data|information))", ans, re.I))
        results.append(item)
    scored = [x for x in results if "correct" in x]
    summ = {
        "questions": len(results),
        "answered_with_citations": sum(1 for x in results if x["citations"] > 0) / len(results),
        "clean_numbers": sum(1 for x in results if not x["unsupported"]) / len(results),
        "accuracy_on_known_facts": (sum(1 for x in scored if x["correct"]) / len(scored)) if scored else None,
        "scored_questions": len(scored),
        "median_latency_ms": sorted(x["latency_ms"] for x in results)[len(results) // 2],
    }
    from services import llm
    with engine.begin() as conn:
        rid = conn.execute(text("INSERT INTO eval_runs (ticker, model, summary_json, results_json) VALUES (:t,:m,:s,:r)"),
                           {"t": t, "m": llm.model_name(), "s": json.dumps(summ), "r": json.dumps(results, default=str)}).lastrowid
    return {"id": rid, "ticker": t, "summary": summ, "results": results}
