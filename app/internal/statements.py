"""
Annual financial statements with provenance on every line.

Primary source: the company's own annual reports filed with the SEC (XBRL company facts).
Each value says which filing it came from. Yahoo Finance is used only to cross-check, and as a
clearly labelled fallback when the SEC has no value for a line (it is then marked "not verified").
"""
from typing import Dict, List

from app.internal.research_data import get_statements as yahoo_statements
from app.internal.sec_facts import annual_statements

ITEMS = ["revenue", "cost_of_revenue", "gross_profit", "operating_income", "net_income", "eps_diluted", "dps",
         "interest_expense", "total_assets", "current_assets", "current_liabilities", "cash", "inventory", "equity",
         "total_debt", "operating_cash_flow", "capex", "free_cash_flow", "dividends_paid", "diluted_shares"]


def _diff(a, b):
    try:
        return abs(a - b) / max(abs(a), abs(b), 1e-9)
    except TypeError:
        return None


# Accounting identities every annual report must satisfy. A failure means we read the wrong
# XBRL concept, the company restated, or the filing uses a different definition.
#   (name, items involved, function -> (reported, expected), tolerance)
TIE_OUTS = [
    ("Assets = liabilities + equity (balance sheet total)", ["total_assets"],
     lambda s: (s["total_assets"], s["liabilities_and_equity"]), 0.005, ["total_assets", "liabilities_and_equity"]),
    ("Gross profit = revenue − cost of revenue", ["gross_profit", "revenue", "cost_of_revenue"],
     lambda s: (s["gross_profit"], s["revenue"] - s["cost_of_revenue"]), 0.01, ["gross_profit", "revenue", "cost_of_revenue"]),
    ("Diluted EPS ≈ net income ÷ diluted shares", ["eps_diluted"],
     lambda s: (s["eps_diluted"], s["net_income"] / s["diluted_shares"]), 0.05, ["eps_diluted", "net_income", "diluted_shares"]),
    ("Current assets ≤ total assets", ["current_assets"],
     lambda s: (min(s["current_assets"], s["total_assets"]), s["current_assets"]), 0.0, ["current_assets", "total_assets"]),
    ("Cash ≤ current assets", ["cash"],
     lambda s: (min(s["cash"], s["current_assets"]), s["cash"]), 0.0, ["cash", "current_assets"]),
    ("Gross profit ≤ revenue", ["gross_profit"],
     lambda s: (min(s["gross_profit"], s["revenue"]), s["gross_profit"]), 0.0, ["gross_profit", "revenue"]),
]


def tie_outs(sec_year: Dict) -> List[Dict]:
    """Run the identities on raw SEC values for one fiscal year. Skips a check when an input is missing."""
    vals = {k: v["value"] for k, v in sec_year.items() if isinstance(v, dict) and v.get("value") is not None}
    out = []
    for name, flags, fn, tol, needs in TIE_OUTS:
        if not all(k in vals for k in needs):
            continue
        try:
            reported, expected = fn(vals)
        except ZeroDivisionError:
            continue
        diff = _diff(reported, expected) or 0.0
        out.append({"check": name, "reported": reported, "expected": expected, "difference": diff,
                    "tolerance": tol, "passed": diff <= tol + 1e-12, "flags": flags})
    return out


def verified_statements(ticker: str, years: int = 4) -> Dict:
    """{"years": [{"fiscal_year_end", "items": {k: v}, "provenance": {k: {...}}}], "currency", "sec_source"}"""
    sec = annual_statements(ticker, years=years + 1)
    try:
        yh = {y["fiscal_year_end"]: y for y in yahoo_statements(ticker)}
    except Exception:
        yh = {}
    out = []
    ends = list(sec["years"].keys())[:years] or list(yh.keys())[:years]
    for end in ends:
        s = sec["years"].get(end, {})
        y = next((v for k, v in yh.items() if abs((_d(k) - _d(end)).days) <= 10), {})  # Yahoo dates can differ by a few days
        items, prov = {}, {}
        for k in ITEMS:
            if k in s:
                items[k] = s[k]["value"]
                prov[k] = {"source": "sec", "form": s[k]["form"], "filed": s[k]["filed"], "concept": s[k]["concept"], "url": s[k]["url"]}
            elif k == "total_debt" and ("long_term_debt" in s or "short_term_debt" in s):
                items[k] = (s.get("long_term_debt", {}).get("value") or 0) + (s.get("short_term_debt", {}).get("value") or 0)
                src = s.get("long_term_debt") or s.get("short_term_debt")
                prov[k] = {"source": "sec_calc", "formula": "long-term debt + current portion / short-term borrowings",
                           "form": src["form"], "filed": src["filed"], "url": src["url"]}
            elif k == "free_cash_flow" and "operating_cash_flow" in s and "capex" in s:
                items[k] = s["operating_cash_flow"]["value"] - abs(s["capex"]["value"])
                prov[k] = {"source": "sec_calc", "formula": "operating cash flow − capital expenditure",
                           "form": s["operating_cash_flow"]["form"], "filed": s["operating_cash_flow"]["filed"], "url": s["operating_cash_flow"]["url"]}
            elif y.get(k) is not None:
                items[k] = y[k]
                prov[k] = {"source": "yahoo", "note": "not in the SEC data for this year — from Yahoo Finance, not verified"}
            else:
                items[k] = None
            # cross-check against Yahoo where both exist
            if prov.get(k, {}).get("source", "").startswith("sec") and y.get(k) is not None:
                d = _diff(abs(items[k]), abs(y[k]))  # sign conventions differ for outflows (capex, dividends)
                prov[k]["yahoo_diff"] = d
        checks = tie_outs(s)
        for c in checks:
            if not c["passed"]:
                for k in c["flags"]:
                    if prov.get(k, {}).get("source", "").startswith("sec"):
                        prov[k]["check_failed"] = c["check"]
        out.append({"fiscal_year_end": end, "items": items, "provenance": prov, "checks": checks})
    verified = sum(1 for yr in out for p in yr["provenance"].values() if p["source"].startswith("sec"))
    total = sum(1 for yr in out for v in yr["items"].values() if v is not None)
    flagged = sum(1 for yr in out for p in yr["provenance"].values() if p.get("check_failed"))
    checks_run = sum(len(yr["checks"]) for yr in out)
    checks_failed = sum(1 for yr in out for c in yr["checks"] if not c["passed"])
    return {"years": out, "currency": sec.get("currency") or "USD", "sec_source": sec.get("source"),
            "coverage": {"from_sec": verified - flagged, "total": total, "flagged": flagged,
                         "checks_run": checks_run, "checks_failed": checks_failed}}


def _d(s):
    from datetime import date
    return date.fromisoformat(s[:10])
