"""
Investment view: an estimate of what a share is worth and a rule-based BUY / HOLD / SELL rating.

Method (the one used in the Managerial Finance team report on Coca-Cola, applied to any company;
the capital-budgeting part of that report is deliberately left out):

  1. Required return (cost of equity), CAPM:   k_e = r_f + beta x ERP
       r_f  = 10-year US Treasury yield
       beta = Blume-adjusted: 0.67 x raw beta + 0.33   (raw = 5 years of monthly returns vs the S&P 500)
       ERP  = equity risk premium, an assumption (default 4.5%, env EQUITY_RISK_PREMIUM)
  2. Three estimates of value per share
       a. Dividend discount model (Gordon growth):  D1 / (k_e - g)
       b. Historical P/E:  average fiscal-year-end P/E x expected earnings per share
       c. Analyst consensus:  average 12-month price target
  3. Blended fair value = equal-weight average of the methods that could be calculated (at least two).
  4. Rating:  BUY  when price < fair value x (1 - 10%)
              SELL when price > fair value x (1 + 10%)
              HOLD otherwise

Every input is returned with its source so the result can be re-calculated by hand. The rating is the
output of this formula only: no AI is involved, and the AI text paths still may not give opinions
(services/policy.py). It is not personal advice.

The functions in the first half are pure (no network) and unit-tested; build() gathers live inputs.
"""
from __future__ import annotations

import os
from typing import Dict, List, Optional, Sequence, Tuple

ERP = float(os.getenv("EQUITY_RISK_PREMIUM", "0.045"))
BAND = float(os.getenv("RATING_BAND", "0.10"))
BLUME = (0.67, 0.33)
MIN_PAYOUT = 0.40          # the dividend model is only used when at least 40% of profit is paid out as dividends
MIN_SPREAD = 0.02          # the dividend model needs k_e to exceed growth by at least 2 points, or it explodes
MAX_SPREAD = float(os.getenv("RATING_MAX_SPREAD", "0.50"))  # no rating when highest − lowest method exceeds this share of fair value
NEAR_LINE = 0.02           # "close to the line" note when the price is within 2% of a band edge
MAX_PE = 200.0             # a year-end P/E above this is treated as not meaningful and left out of the average
FALLBACK_RISK_FREE = 0.042

# Model portfolio from the report: the stock as a 15% core holding plus low-cost index funds.
PORTFOLIO = [
    # symbol, name, asset class, weight, kind, expense ratio (fund fact sheets, Nov 2026)
    (None, None, "Stock", 0.15, "stock", None),
    ("VTI", "Vanguard Total Stock Market", "US stocks fund", 0.30, "equity", 0.0003),
    ("VXUS", "Vanguard Total International Stock", "International stocks fund", 0.15, "equity", 0.0005),
    ("BND", "Vanguard Total Bond Market", "Investment-grade bond fund", 0.25, "bond", 0.0003),
    ("SGOV", "iShares 0-3 Month Treasury", "Treasury-bill fund (cash-like)", 0.10, "cash", 0.0009),
    ("VNQ", "Vanguard Real Estate", "US real-estate fund", 0.05, "reit", 0.0013),
]
# Bear-market stress test from the report: broad stocks -30%, the stock -30% x its adjusted beta,
# real estate -20%, bonds +3%, Treasury bills +2%.
STRESS = {"equity": -0.30, "reit": -0.20, "bond": 0.03, "cash": 0.02}


# ============================================================================ pure calculations
def blume(raw_beta: float) -> float:
    """Raw betas drift toward 1.0 over time; the Blume adjustment moves them a third of the way there."""
    return BLUME[0] * raw_beta + BLUME[1]


def cost_of_equity(risk_free: float, raw_beta: float, erp: float = ERP) -> Dict:
    b = blume(raw_beta)
    return {"risk_free": risk_free, "raw_beta": raw_beta, "beta": b, "erp": erp, "ke": risk_free + b * erp,
            "formula": "risk-free rate + adjusted beta × equity risk premium"}


def dividend_growth(history: Sequence[Tuple[int, float]]) -> Optional[Dict]:
    """Compound yearly growth of dividends per share from the first to the last full year (needs 4+ years)."""
    pts = [(int(y), float(d)) for y, d in history if d and d > 0]
    if len(pts) < 4:
        return None
    (y0, d0), (y1, d1) = pts[0], pts[-1]
    n = y1 - y0
    if n < 3:
        return None
    return {"rate": (d1 / d0) ** (1 / n) - 1, "from_year": y0, "to_year": y1, "years": n, "from_dps": d0, "to_dps": d1}


def ddm(d0: Optional[float], growth: Optional[Dict], ke: float, payout: Optional[float] = None) -> Dict:
    """Gordon growth: next year's dividend ÷ (required return − growth). Growth is the company's own
    dividend growth, kept between 0 and (required return − 2 points). Only for companies that pay out
    a large part of their profit: for a low-payout company dividends say little about its worth and the
    model gives a value far below the other methods (seen live: about $32 for a $340 stock)."""
    name = "Dividend discount model"
    if not d0 or d0 <= 0:
        return {"key": "ddm", "name": name, "available": False, "why": "the company pays no dividend, so this method doesn't apply"}
    if payout is not None and payout < MIN_PAYOUT:
        return {"key": "ddm", "name": name, "available": False,
                "why": f"the company pays out only {payout * 100:.0f}% of its profit as dividends (the method needs at least "
                       f"{MIN_PAYOUT * 100:.0f}%), so dividends say little about what a share is worth"}
    if not growth:
        return {"key": "ddm", "name": name, "available": False, "why": "fewer than 4 full years of dividend history"}
    g_hist = growth["rate"]
    g = min(max(g_hist, 0.0), ke - MIN_SPREAD)
    if g < 0:
        return {"key": "ddm", "name": name, "available": False, "why": "the required return is too low for this method to give a sensible number"}
    d1 = d0 * (1 + g)
    rows = []
    for dk in (-0.005, 0.0, 0.005, 0.01):
        row = {"ke": ke + dk, "values": []}
        for dg in (-0.01, -0.005, 0.0):
            gg = g + dg
            row["values"].append({"g": gg, "value": d0 * (1 + gg) / (ke + dk - gg) if ke + dk - gg >= 0.01 and gg >= 0 else None})
        rows.append(row)
    return {"key": "ddm", "name": name, "available": True, "value": d1 / (ke - g), "d0": d0, "d1": d1, "g": g, "g_history": g_hist,
            "g_capped": abs(g - g_hist) > 1e-9, "ke": ke, "growth": growth, "sensitivity": rows,
            "formula": "next year's dividend ÷ (required return − dividend growth)"}


def pe_method(history: Sequence[Dict], eps: Optional[float], eps_basis: str) -> Dict:
    """Average fiscal-year-end P/E × expected earnings per share. history rows: {year, price, eps}."""
    name = "Historical P/E"
    rows = []
    for h in history:
        if h.get("price") and h.get("eps") and h["eps"] > 0:
            pe = h["price"] / h["eps"]
            rows.append({**h, "pe": pe, "used": pe <= MAX_PE})
    used = [r["pe"] for r in rows if r["used"]]
    if len(used) < 2:
        return {"key": "pe", "name": name, "available": False, "rows": rows,
                "why": "fewer than two years with positive earnings and a year-end price"}
    if not eps or eps <= 0:
        return {"key": "pe", "name": name, "available": False, "rows": rows, "why": "earnings per share are not positive"}
    avg = sum(used) / len(used)
    return {"key": "pe", "name": name, "available": True, "value": avg * eps, "avg_pe": avg, "eps": eps, "eps_basis": eps_basis,
            "rows": rows, "years": len(used), "formula": "average year-end P/E × expected earnings per share"}


def analyst_method(target: Optional[float], count: Optional[int]) -> Dict:
    name = "Analyst consensus target"
    if not target or target <= 0:
        return {"key": "analyst", "name": name, "available": False, "why": "no analyst price targets found"}
    return {"key": "analyst", "name": name, "available": True, "value": float(target), "count": count,
            "formula": "average 12-month price target of covering analysts"}


def rate(price: Optional[float], fair: Optional[float], band: float = BAND) -> Dict:
    """BUY / HOLD / SELL from the price's distance to fair value."""
    if not price or not fair:
        return {"rating": None}
    lo, hi = fair * (1 - band), fair * (1 + band)
    r = "BUY" if price < lo else "SELL" if price > hi else "HOLD"
    return {"rating": r, "buy_below": lo, "sell_above": hi, "band": band, "gap": fair / price - 1,
            "rule": f"BUY if the price is more than {band * 100:.0f}% below fair value, SELL if more than {band * 100:.0f}% above, otherwise HOLD"}


def assess(i: Dict) -> Dict:
    """Pure: all inputs in, full valuation out. See build() for the keys of `i`."""
    usd = (i.get("currency") or "USD") == "USD"
    coe = cost_of_equity(i["risk_free"], i["raw_beta"], i.get("erp", ERP))
    if usd:
        m_ddm = ddm(i.get("d0"), dividend_growth(i.get("dps_history") or []), coe["ke"], i.get("payout"))
        m_pe = pe_method(i.get("pe_history") or [], i.get("eps"), i.get("eps_basis") or "")
    else:
        why = (f"the company reports to the SEC in {i['currency']} per ordinary share, while the US-listed price is in dollars "
               f"per depositary share, so the two can't be combined without the share ratio")
        m_ddm = {"key": "ddm", "name": "Dividend discount model", "available": False, "why": why}
        m_pe = {"key": "pe", "name": "Historical P/E", "available": False, "why": why, "rows": []}
    m_an = analyst_method(i.get("analyst_target"), i.get("analyst_count"))
    methods = [m_ddm, m_pe, m_an]
    price = i.get("price")
    vals = [m["value"] for m in methods if m["available"]]
    for m in methods:
        if m["available"] and price:
            m["vs_price"] = m["value"] / price - 1
    fair = sum(vals) / len(vals) if len(vals) >= 2 else None
    rating = rate(price, fair)
    if fair is None:
        rating["why_none"] = ("Only one of the three methods could be calculated, and a single estimate isn't enough for a rating."
                              if vals else "None of the three methods could be calculated.")
    else:
        rating["spread"] = (max(vals) - min(vals)) / fair
        rating["low"], rating["high"] = min(vals), max(vals)
        if rating["spread"] > MAX_SPREAD and rating["rating"]:
            # the methods disagree too much for their average to mean much: say so instead of rating
            rating["indicative"], rating["rating"] = rating["rating"], None
            rating["why_none"] = (f"The methods disagree too much: the highest is more than {MAX_SPREAD * 100:.0f}% of fair value above the lowest, "
                                  f"so their average isn't a dependable estimate.")
        elif rating["rating"] and price:
            edge = min(abs(price / rating["buy_below"] - 1), abs(price / rating["sell_above"] - 1))
            rating["near_line"] = edge <= NEAR_LINE
    out = {"ticker": i["ticker"], "name": i.get("name") or i["ticker"], "currency": i.get("currency") or "USD",
           "price": price, "price_source": i.get("price_source"), "price_as_of": i.get("price_as_of"),
           "cost_of_equity": coe, "methods": methods, "methods_used": len(vals), "fair_value": fair, **rating,
           "inputs": i.get("sources") or [], "assumptions": [
               f"Equity risk premium {coe['erp'] * 100:.1f}% (the extra yearly return investors expect from stocks over Treasuries; an assumption)",
               f"Beta adjusted with the Blume formula ({BLUME[0]} × raw beta + {BLUME[1]})",
               "Dividend growth = the company's own past growth, kept at least 2 points below the required return",
               f"The dividend method is used only when the company pays out at least {MIN_PAYOUT * 100:.0f}% of its profit",
               "The three methods get equal weight",
               f"Rating bands are ±{BAND * 100:.0f}% around fair value",
               f"No rating is given when the highest and lowest method are more than {MAX_SPREAD * 100:.0f}% of fair value apart"]}
    out["dividends"] = dividend_policy(i, coe)
    out["risks"] = risk_checks(i, out)
    return out


def dividend_policy(i: Dict, coe: Dict) -> Dict:
    hist = [(int(y), float(d)) for y, d in (i.get("dps_history") or []) if d]
    streak = 0
    for k in range(len(hist) - 1, 0, -1):
        if hist[k][1] > hist[k - 1][1]:
            streak += 1
        else:
            break
    price, d0 = i.get("price"), i.get("d0")
    usd = (i.get("currency") or "USD") == "USD"
    return {"pays": bool(d0), "history": [{"year": y, "dps": d} for y, d in hist], "raises_in_a_row": streak,
            "history_years": len(hist), "growth": dividend_growth(hist), "d0": d0,
            "yield": d0 / price if d0 and price and usd else None, "risk_free": coe["risk_free"],
            "years": i.get("payout_years") or []}


def risk_checks(i: Dict, v: Dict) -> List[Dict]:
    """Rule-based checks that can be measured from the data. Each states its rule; none is an opinion.
    Company-specific risks (lawsuits, regulation, product trends) are not measurable here: the AI analyst
    can read them from the annual report's risk section on request."""
    out = []
    price, pe = v.get("price"), next(m for m in v["methods"] if m["key"] == "pe")
    eps_last = i.get("eps_last")
    if pe.get("avg_pe") and price and eps_last and eps_last > 0:
        cur = price / eps_last
        prem = cur / pe["avg_pe"] - 1
        out.append({"risk": "Price tag (valuation)", "level": "High" if prem > 0.20 else "Medium" if prem > 0.05 else "Low",
                    "cur_pe": cur, "avg_pe": pe["avg_pe"], "premium": prem, "derate": pe["avg_pe"] / cur - 1,
                    "rule": "P/E today vs its own average: more than 20% above = High, 5–20% above = Medium, otherwise Low"})
    d = v["dividends"]
    if d.get("yield") is not None:
        gap = d["risk_free"] - d["yield"]
        out.append({"risk": "Interest rates", "level": "Medium" if gap > 0 else "Low", "yield": d["yield"], "risk_free": d["risk_free"],
                    "rule": "Dividend yield below the 10-year Treasury yield = Medium, otherwise Low"})
    cov, de = i.get("interest_coverage"), i.get("debt_to_equity")
    if cov is not None:
        out.append({"risk": "Debt", "level": "High" if cov < 3 else "Medium" if cov < 6 else "Low", "coverage": cov, "debt_to_equity": de,
                    "rule": "Operating profit ÷ interest: under 3 times = High, 3–6 = Medium, above 6 = Low"})
    b = v["cost_of_equity"]["raw_beta"]
    out.append({"risk": "Moves with the market", "level": "High" if b > 1.2 else "Medium" if b >= 0.8 else "Low", "beta": b,
                "rule": "Raw beta above 1.2 = High, 0.8–1.2 = Medium, below 0.8 = Low"})
    vals = [m["value"] for m in v["methods"] if m["available"]]
    if len(vals) >= 2 and v.get("fair_value"):
        spread = (max(vals) - min(vals)) / v["fair_value"]
        out.append({"risk": "The estimate itself", "level": "High" if spread > 0.30 else "Medium" if spread > 0.15 else "Low",
                    "spread": spread, "low": min(vals), "high": max(vals),
                    "rule": "Gap between the highest and lowest method: over 30% of fair value = High, 15–30% = Medium, otherwise Low"})
    return out


def model_portfolio(ticker: str, name: str, adj_beta: float, risk_free: float, erp: float, stock_yield: Optional[float],
                    funds: Dict[str, Dict], budget: float = 100_000.0) -> Dict:
    """The report's diversified portfolio with this stock as the 15% core holding.
    funds: {symbol: {"beta": float|None, "yield": float|None}}. Stock funds get a CAPM expected return;
    bond and Treasury funds are given beta 0 and an expected return equal to their yield (the report's assumptions)."""
    rows = []
    for sym, nm, cls, w, kind, fee in PORTFOLIO:
        if kind == "stock":
            sym, nm, beta, yld = ticker, name, adj_beta, stock_yield
            shock = STRESS["equity"] * adj_beta
        else:
            f = funds.get(sym) or {}
            yld = f.get("yield")
            beta = 0.0 if kind in ("bond", "cash") else f.get("beta")
            shock = STRESS[kind]
        exp = (yld if kind in ("bond", "cash") else (risk_free + beta * erp if beta is not None else None))
        rows.append({"symbol": sym, "name": nm, "asset_class": cls, "kind": kind, "weight": w, "amount": budget * w, "beta": beta,
                     "yield": yld, "expected_return": exp, "expense_ratio": fee, "stress": shock})

    def wsum(k):
        return None if any(r[k] is None for r in rows) else sum(r["weight"] * r[k] for r in rows)
    total = {"beta": wsum("beta"), "yield": wsum("yield"), "expected_return": wsum("expected_return"),
             "expense_ratio": sum(r["weight"] * (r["expense_ratio"] or 0) for r in rows), "stress": wsum("stress")}
    total["income"] = total["yield"] * budget if total["yield"] is not None else None
    total["fees"] = total["expense_ratio"] * budget
    w0 = rows[0]["weight"]
    return {"budget": budget, "rows": rows, "total": total,
            "mix": {"stocks": sum(r["weight"] for r in rows if r["kind"] in ("stock", "equity")),
                    "real_estate": sum(r["weight"] for r in rows if r["kind"] == "reit"),
                    "bonds_cash": sum(r["weight"] for r in rows if r["kind"] in ("bond", "cash"))},
            "position_sizing": {"weight": w0, "shock": -0.25, "portfolio_cost": w0 * -0.25},
            "stress_scenario": "broad stocks −30%, this stock −30% × its adjusted beta, real estate −20%, bonds +3%, Treasury bills +2%",
            "rebalance": "once a year, or when any holding drifts more than 5 percentage points from its target",
            "assumptions": ["Weights are the template from the team report (15% stock, 60% stocks in total, 5% real estate, 35% bonds and Treasury bills) "
                            "for a moderate-risk, long-horizon investor; they are not tailored to you",
                            "Expected return for stock holdings = risk-free rate + beta × equity risk premium (CAPM); for bond and Treasury funds = current yield",
                            "Bond and Treasury funds are given a beta of 0 against stocks",
                            "Expense ratios are from the fund fact sheets as of November 2026"]}


# ============================================================================ live inputs
def _monthly_beta(px, t: str, m: str = "SPY") -> Optional[float]:
    import numpy as np
    if px is None or px.empty or t not in px or m not in px:
        return None
    df = px[[t, m]].dropna()
    try:
        mo = df.resample("ME").last()
    except ValueError:  # pandas < 2.2
        mo = df.resample("M").last()
    r = mo.pct_change().dropna()
    if len(r) < 24:
        return None
    cov = np.cov(r[t], r[m])
    return float(cov[0, 1] / cov[1, 1]) if cov[1, 1] else None


def gather(ticker: str) -> Dict:
    """Collect every input with its source. Network: SEC (cached), Yahoo prices/dividends/profile, the price store."""
    from app.internal.research_data import get_closes, get_dividends, get_macro, get_prices, get_profile
    from app.internal.statements import verified_statements
    from app.routers.research import market_price

    t = ticker.upper()
    prof = get_profile(t)
    mp = market_price(t)
    st = verified_statements(t, years=5)
    cur = st.get("currency") or "USD"
    if prof.get("financial_currency") and prof["financial_currency"] != "USD":
        cur = prof["financial_currency"]  # foreign filer: statements are not in dollars even when the SEC data doesn't say so
    years = st["years"]
    src = []

    macro = get_macro()
    rf = macro.get("ten_year_yield")
    src.append({"input": "Risk-free rate", "value": rf or FALLBACK_RISK_FREE, "unit": "%",
                "source": f"10-year US Treasury yield (Yahoo Finance ^TNX, {macro.get('as_of')}; not verified)" if rf
                else "fallback value — the Treasury yield could not be loaded", "url": "https://finance.yahoo.com/quote/%5ETNX"})
    rf = rf or FALLBACK_RISK_FREE

    px = get_prices([t, "SPY"], years=5)
    raw = _monthly_beta(px, t)
    basis = "5 years of monthly price changes vs the S&P 500 (SPY), calculated by Oracle from Yahoo Finance prices"
    if raw is None and prof.get("beta_yahoo") is not None:
        raw, basis = prof["beta_yahoo"], "Yahoo Finance's published beta (not verified) — too little price history to calculate it"
    if raw is None:
        raw, basis = 1.0, "assumed 1.0 (moves like the market) — no beta could be calculated"
    src.append({"input": "Raw beta", "value": raw, "unit": "x", "source": basis, "url": f"https://finance.yahoo.com/quote/{t}/history"})
    src.append({"input": "Equity risk premium", "value": ERP, "unit": "%",
                "source": "assumption: midpoint of Damodaran's 2026 implied estimates (4.23%–4.77%), as in the team report",
                "url": "https://pages.stern.nyu.edu/~adamodar/"})
    src.append({"input": "Share price", "value": mp.get("price"), "unit": "$", "source": f"{mp.get('source')}, {mp.get('as_of')}", "url": None})

    # dividends: last 12 months of payments, and up to 10 full years of history
    try:
        dv = get_dividends(t)
    except Exception:
        dv = {"annual": [], "ttm_dps": None}
    d0 = dv.get("ttm_dps") or None
    hist = [(a["year"], a["dps"]) for a in dv.get("annual", [])]
    if d0:
        src.append({"input": "Dividends per share, last 12 months", "value": d0, "unit": "$",
                    "source": "sum of actual payments (Yahoo Finance; not verified)", "url": f"https://finance.yahoo.com/quote/{t}/history?filter=div"})

    # historical P/E: fiscal-year-end close (not dividend-adjusted) ÷ that year's diluted EPS from the SEC
    pe_hist, payout = [], []
    try:
        closes = get_closes(t, years=6)
    except Exception:
        closes = None
    import pandas as pd
    for y in years:
        it, fye = y["items"], y["fiscal_year_end"]
        p = None
        if closes is not None and len(closes):
            upto = closes[closes.index <= pd.Timestamp(fye)]
            if len(upto) and (pd.Timestamp(fye) - upto.index[-1]).days <= 7:
                p = float(upto.iloc[-1])
        prov = (y.get("provenance") or {}).get("eps_diluted") or {}
        pe_hist.append({"year": fye[:4], "fiscal_year_end": fye, "price": p, "eps": it.get("eps_diluted"), "url": prov.get("url"),
                        "eps_source": "SEC" if str(prov.get("source", "")).startswith("sec") else "Yahoo (not verified)"})
        fcf, paid = it.get("free_cash_flow"), it.get("dividends_paid")
        payout.append({"year": fye[:4], "dps": it.get("dps"), "eps": it.get("eps_diluted"),
                       "payout": it["dps"] / it["eps_diluted"] if it.get("dps") and it.get("eps_diluted") and it["eps_diluted"] > 0 else None,
                       "dividends_paid": abs(paid) if paid is not None else None, "free_cash_flow": fcf,
                       "fcf_cover": fcf / abs(paid) if fcf is not None and paid else None})
    eps_last = years[0]["items"].get("eps_diluted") if years else None
    fwd = prof.get("forward_eps")
    if fwd and fwd > 0 and cur == "USD":
        eps, eps_basis = fwd, "analysts' average estimate for the next fiscal year (Yahoo Finance; not verified)"
    else:
        eps, eps_basis = eps_last, f"last full fiscal year ({years[0]['fiscal_year_end'][:4]}), as reported to the SEC" if years else ""
    if eps:
        src.append({"input": "Expected earnings per share", "value": eps, "unit": "$", "source": eps_basis,
                    "url": (years[0].get("provenance", {}).get("eps_diluted") or {}).get("url") if eps is eps_last and years else f"https://finance.yahoo.com/quote/{t}/analysis"})
    if prof.get("analyst_target_mean"):
        src.append({"input": "Analysts' average price target", "value": prof["analyst_target_mean"], "unit": "$",
                    "source": f"{prof.get('analyst_count') or 'several'} analysts (Yahoo Finance; not verified)", "url": f"https://finance.yahoo.com/quote/{t}/analysis"})

    it0 = years[0]["items"] if years else {}
    ie, oi = it0.get("interest_expense"), it0.get("operating_income")
    return {"ticker": t, "name": prof.get("name") or t, "currency": cur, "price": mp.get("price"), "price_source": mp.get("source"),
            "price_as_of": mp.get("as_of"), "risk_free": rf, "raw_beta": raw, "erp": ERP, "d0": d0, "dps_history": hist,
            "pe_history": list(reversed(pe_hist)), "eps": eps, "eps_basis": eps_basis, "eps_last": eps_last,
            "analyst_target": prof.get("analyst_target_mean"), "analyst_count": prof.get("analyst_count"),
            "payout_years": list(reversed(payout)), "payout": payout[0]["payout"] if payout else None,
            "interest_coverage": oi / abs(ie) if oi is not None and ie else None,
            "debt_to_equity": it0["total_debt"] / it0["equity"] if it0.get("total_debt") is not None and it0.get("equity") else None,
            "sources": src}


def build(ticker: str) -> Dict:
    """Valuation, rating, dividend policy and risk checks for one company, with plain-language text."""
    from app.internal.explain import rating_story
    from app.internal.research_data import cached
    def load():
        v = assess(gather(ticker))
        v["story"] = rating_story(v)
        v["note"] = ("Rule-based result from the formula shown, using the listed inputs and assumptions. "
                     "For study and research; not personal investment advice.")
        return v
    return cached(f"valuation:{ticker.upper()}", load, ttl=900)


def build_portfolio(ticker: str, budget: float = 100_000.0) -> Dict:
    from app.internal.research_data import cached, get_dividends, get_prices

    def load():
        v = build(ticker)
        syms = [p[0] for p in PORTFOLIO if p[0]]
        px = get_prices(syms + ["SPY"], years=5)
        funds = {}
        for s in syms:
            yld = None
            try:
                ttm = get_dividends(s).get("ttm_dps")
                last = float(px[s].dropna().iloc[-1]) if s in px and px[s].dropna().size else None
                yld = ttm / last if ttm and last else None
            except Exception:
                pass
            funds[s] = {"beta": _monthly_beta(px, s), "yield": yld}
        coe = v["cost_of_equity"]
        out = model_portfolio(v["ticker"], v["name"], coe["beta"], coe["risk_free"], coe["erp"], v["dividends"].get("yield") or 0.0, funds, budget)
        out["ticker"], out["rating"] = v["ticker"], v.get("rating")
        out["buy_below"] = v.get("buy_below")
        out["source"] = "Fund prices and distributions: Yahoo Finance (not verified). Betas: 5 years of monthly price changes vs SPY."
        from app.internal.explain import portfolio_story
        out["story"] = portfolio_story(out)
        return out
    return cached(f"modelpf:{ticker.upper()}:{int(budget)}", load, ttl=3600)
