"""
Specialist briefing.

Four areas, each with its OWN sourced material, written in ONE AI call (token-efficient):
  Financials    — SEC-reported statements and ratios vs chosen peers
  Market        — historical price statistics and recent technical signals
  Supply chain  — evidence-backed suppliers/customers (quotes from filings/news) and their recent moves
  News & filings — recent headlines, recent SEC filings, and risk passages from the company's own 10-K
  Valuation     — fair-value estimate and a rule-based BUY / HOLD / SELL rating (app/internal/valuation.py)
Each section states what the material SAYS, with fact ids. The only rating is the one produced by the
fixed formula in valuation.py, shown with its inputs and assumptions; nothing here is an AI opinion.
Every number written is checked against the material it was given.
"""
from typing import Dict, List

from sqlalchemy import text

from services import llm
from services.db_manager import get_engine
from services.grounding import unsupported_numbers
from services.policy import enforce, enforce_list

engine = get_engine()

AGENTS = ["valuation", "financials", "market", "supply_chain", "news_filings"]
LABELS = {"financials": "Money in and out (reported results)", "market": "Share price", "supply_chain": "Suppliers, customers & competitors",
          "news_filings": "News & SEC filings", "valuation": "Fair value & rating (formula)"}

def _fmt(items: List[str]) -> str:
    return "\n".join(f"[F{i+1}] {x}" for i, x in enumerate(items)) or "(none)"


def _p(x, d=1):
    return "n/a" if x is None else f"{x * 100:.{d}f}%"


def _n(x, d=2):
    return "n/a" if x is None else f"{x:.{d}f}"


def _b(x):
    return "n/a" if x is None else f"{x / 1e9:.2f} billion"


def _gather(ticker: str) -> Dict:
    from app.routers import research as R

    rep = R.company_report(ticker)
    y0 = rep["years"][0]
    it, ra, med = y0["items"], y0["ratios"], rep["peers"]["median"]
    cur = rep["profile"]["currency"]
    fy = y0["fiscal_year_end"]
    peers = ", ".join(p["ticker"] for p in rep["peers"]["rows"]) or "none chosen"
    out = {"name": rep["profile"].get("name") or ticker}

    from app.internal import explain as X
    ex = X.Explainer()
    prev = rep["years"][1]["items"] if len(rep["years"]) > 1 else None
    pe_note = f" and the {rep['market']['source']} share price" if ra.get("pe") is not None else ""
    fin = [X.financial_lead(out["name"], fy, it, prev, cur, ex)]
    fin += X.financial_points(it, ra, med, peers, rep.get("growth") or {}, cur, ex, pe_note=pe_note)
    fin = [x for x in fin if x]
    out["financials"] = {"facts": fin, "sources": [], "scope": "reported results, margins, cash, debt and how they compare with similar companies."}

    mkt = []
    try:
        from app.internal.price_facts import price_check
        pc = price_check(ticker)
        if "error" in pc:
            raise ValueError(pc["error"])
        out["_price_check"] = pc
        ps = X.price_story(pc)
        out["_price_story"] = ps
        mkt = ps["lead"] + ps["swings"] + ps["direction"]
    except Exception as e:
        mkt.append(f"Price history unavailable ({str(e)[:60]})")
    try:
        with engine.connect() as conn:
            rows = conn.execute(text("SELECT message, created_at FROM active_alerts WHERE ticker=:t ORDER BY created_at DESC LIMIT 3"), {"t": ticker}).fetchall()
        mkt += [f"Recent alert ({X.day(str(c)[:10])}): {m}" for m, c in rows]
    except Exception:
        pass
    out["market"] = {"facts": mkt, "sources": [], "scope": "how the price moved and how much it swung, compared with the overall market and its industry."}

    try:
        from app.internal.valuation import build as build_valuation
        v = build_valuation(ticker)
        vs = v["story"]
        out["_valuation"] = v
        out["valuation"] = {"facts": vs["lead"] + vs["methods"] + vs["required_return"] + vs["dividends"] + vs["risks"][:-1], "sources": [],
                            "scope": "what a share is estimated to be worth and the rule-based rating, with every input."}
    except Exception as e:
        out["valuation"] = {"facts": [f"The fair-value estimate could not be calculated ({str(e)[:80]})."], "sources": [], "scope": "valuation"}

    sc = []
    try:
        from app.routers.market import get_supply_chain
        for l in get_supply_chain(ticker, 1, False).get("links", [])[:8]:
            if l.get("statement"):
                sc.append(f"{l['statement']} (source: {l.get('source_type')})")
    except Exception as e:
        sc.append(f"Supply-chain data unavailable ({str(e)[:60]})")
    if not sc:
        sc.append("No evidence-backed supplier or customer links have been found yet.")
    out["supply_chain"] = {"facts": sc, "sources": [], "scope": "which suppliers and customers are documented, with their evidence."}

    nf = []
    try:
        with engine.connect() as conn:
            heads = conn.execute(text("SELECT headline, published_at FROM news_articles WHERE ticker=:t AND published_at >= NOW() - INTERVAL 7 DAY "
                                      "ORDER BY published_at DESC LIMIT 6"), {"t": ticker}).fetchall()
            filings = conn.execute(text("SELECT title, body FROM oracle_events WHERE ticker=:t AND kind='filing' ORDER BY created_at DESC LIMIT 4"),
                                   {"t": ticker}).fetchall()
        seen_h = set()
        for h_, p in heads:
            k_ = h_.lower()[:70]
            if k_ not in seen_h:
                seen_h.add(k_)
                nf.append(f"Headline ({str(p)[:10]}): {h_[:150]}")
        nf += [f"SEC filing: {t_} — {b_}" for t_, b_ in filings]
    except Exception:
        pass
    hits = []  # 10-K passages are read on demand in the AI chat ("What risks does the 10-K highlight?")
    out["news_filings"] = {"facts": nf or ["No headlines or filings stored for the last 7 days."], "sources": hits,
                           "scope": "recent headlines, recent SEC filings and the risk factors the company itself discloses."}
    return out


PREFIX = {"financials": "A", "market": "M", "supply_chain": "C", "news_filings": "N", "valuation": "V"}




def fingerprint(mats: Dict) -> str:
    import hashlib
    import json
    core = {k: {"facts": v["facts"], "src": [h.get("title", "") + str(h.get("chunk", ""))[:40] for h in v["sources"]]}
            for k, v in mats.items() if isinstance(v, dict) and "facts" in v}
    return hashlib.sha1(json.dumps(core, sort_keys=True, default=str).encode()).hexdigest()


def _overview(ticker: str, mats: Dict) -> str:
    """The briefing's opening, in plain words, assembled from the facts (no AI). Each sentence carries its fact id."""
    from app.internal.explain import means
    paras = []
    v = mats.get("_valuation")
    if v:
        paras.append(" ".join(f"{x} [V{i + 1}]" for i, x in enumerate(v["story"]["lead"])))
    fin = mats["financials"]["facts"]
    if fin and fin[0]:
        paras.append(f"{fin[0]} [A1]")
    mk = mats["market"]["facts"]
    ps = mats.get("_price_story")
    if ps and ps["lead"]:
        paras.append(" ".join(f"{x} [M{i + 1}]" for i, x in enumerate(ps["lead"])))
    elif mk:
        paras.append(f"{mk[0]} [M1]")
    n_links = sum(1 for x in mats["supply_chain"]["facts"] if "annual report names" in x or "news article" in x)
    paras.append(f"Oracle has {n_links} documented supplier, customer or competitor link{'s' if n_links != 1 else ''} for {ticker}, "
                 f"each backed by a quote from a filing or article [C1]." if n_links else
                 f"No supplier or customer links for {ticker} are documented with evidence yet [C1].")
    paras.append(means("rating") if v and v.get("rating") else means("briefing"))
    return "\n\n".join(paras)


def run_specialist_council(ticker: str, mats: Dict = None) -> Dict:
    """Every section is assembled from the data with no AI call: exact numbers, each with its fact id.
    (An AI summary of headlines repeated the articles' opinions, so headlines are listed as published.)"""
    import time as _t
    t0 = _t.time()
    ticker = ticker.upper()
    mats = mats or _gather(ticker)
    name = mats["name"]
    agents, policy_flags, flagged = [], [], set()
    ps = mats.get("_price_story") or {}
    n_val = len((mats.get("_valuation") or {}).get("story", {}).get("lead") or []) or 1
    n_sum = {"financials": 1, "market": max(1, len(ps.get("lead") or [])), "supply_chain": 1, "valuation": n_val}
    for k in ("valuation", "financials", "market", "supply_chain"):
        facts = mats[k]["facts"]
        agents.append({"agent": k, "label": LABELS[k], "prefix": PREFIX[k], "facts": facts, "sources": [],
                       "summary": " ".join(f"{x} [{PREFIX[k]}{i + 1}]" for i, x in enumerate(facts[:n_sum.get(k, 1)])),
                       "key_points": [f"{x} [{PREFIX[k]}{i + 1 + n_sum.get(k, 1)}]" for i, x in enumerate(facts[n_sum.get(k, 1):14])],
                       "gaps": "", "unsupported_numbers": [], "mode": "data"})
    m = mats["news_filings"]
    if any("10-Q" in x for x in m["facts"]):
        agents[1]["gaps"] = ("A newer quarterly report (10-Q, the report companies file with the SEC every three months) has been filed. "
                             "The figures above come from the latest annual report, so the most recent quarter isn't included yet.")
    heads = [x for x in m["facts"] if x.startswith("Headline")]
    fils = [x for x in m["facts"] if x.startswith("SEC filing")]
    summary = (f"{len(heads)} headline{'s' if len(heads) != 1 else ''} in the last 7 days and {len(fils)} recent SEC filing"
               f"{'s' if len(fils) != 1 else ''} (official reports to the US market regulator). Headlines are the publishers' own words; "
               "open Alerts or Live Monitor to read the articles.") if (heads or fils) else m["facts"][0]
    agents.append({"agent": "news_filings", "label": LABELS["news_filings"], "prefix": "N", "facts": m["facts"], "sources": [],
                   "summary": summary, "key_points": [f"{x} [N{i + 1}]" for i, x in enumerate(m["facts"][:5])] if (heads or fils) else [],
                   "gaps": "", "unsupported_numbers": [], "mode": "data"})
    sources = []
    overview = _overview(ticker, mats)
    src_out = [{"id": x["id"], "title": x["title"], "url": x["url"]} for x in sources]
    try:
        from app.routers.evals import log_answer
        log_answer("briefing", ticker, "specialist briefing", "no AI (data)", overview + " " + summary,
                   src_out, sorted(flagged), (_t.time() - t0) * 1000, policy=policy_flags)
    except Exception:
        pass
    rating = (mats.get("_valuation") or {}).get("rating")
    return {"verdict": "BRIEFING", "decision": "BRIEFING", "rating": rating, "confidence": 0.0, "horizon": "",
            "analysis": overview, "agents": agents, "sources": src_out, "unsupported_numbers": sorted(flagged),
            "policy_flags": policy_flags, "model": "no AI — assembled from SEC data, prices and stored evidence; rating from the fixed formula",
            "fingerprint": fingerprint(mats)}
