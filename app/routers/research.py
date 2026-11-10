"""
Research API — facts first, plus one rule-based investment view.

Every number here is either
  • reported by the company to the SEC (XBRL annual-report data; each line links to its filing),
  • a market price (Alpaca IEX bars, or Yahoo Finance daily prices — labelled as such), or
  • a standard calculation on those (ratio formulas shown alongside).
Lines the SEC data doesn't cover come from Yahoo and are marked "not verified".

The one exception to "facts only" is /{ticker}/valuation (app/internal/valuation.py): a fair-value estimate
and a BUY / HOLD / SELL rating produced by a fixed, published formula (CAPM, dividend discount model,
historical P/E, analyst consensus, ±10% bands). Its assumptions are listed in the response. No AI is involved.
"""
from __future__ import annotations

import re
from typing import Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import text

from app.internal import finance as fx
from app.internal.research_data import get_macro, get_prices, get_profile
from app.internal.statements import verified_statements

router = APIRouter()

VALID_SYMBOL = re.compile(r"^[A-Z]{1,5}([.-][A-Z]{1,2})?$")
FALLBACK_RISK_FREE = 0.042

# Ratios Oracle shows: all computed from SEC-reported lines (plus price for P/E, P/B, yield).
RATIO_DEFS = [d for d in fx.RATIO_DEFS if d[0] != "ev_ebitda"]  # EBITDA isn't an SEC-reported line


def _norm(sym: str) -> str:
    s = (sym or "").strip().upper()
    if not VALID_SYMBOL.match(s):
        raise HTTPException(status_code=400, detail=f"'{sym}' is not a valid US ticker symbol.")
    return s


def _engine():
    from services.db_manager import get_engine
    return get_engine()


def _active_watchlist() -> List[str]:
    try:
        with _engine().connect() as conn:
            rows = conn.execute(text("SELECT symbol FROM tickers WHERE is_active=1 ORDER BY symbol")).fetchall()
        return [r[0].upper() for r in rows if r[0] and VALID_SYMBOL.match(r[0].upper())]
    except Exception:
        return []


def market_price(ticker: str) -> Dict:
    """Latest price with its source: the stored Alpaca IEX bar if recent, else Yahoo's quote."""
    try:
        with _engine().connect() as conn:
            row = conn.execute(text("SELECT close, timestamp FROM market_data WHERE ticker=:t ORDER BY timestamp DESC LIMIT 1"),
                               {"t": ticker}).fetchone()
            if row:
                from datetime import datetime, timedelta
                if datetime.utcnow() - row[1] < timedelta(days=5):
                    return {"price": float(row[0]), "as_of": f"{row[1]} UTC", "source": "Alpaca (IEX exchange bars)"}
    except Exception:
        pass
    prof = get_profile(ticker)
    return {"price": prof.get("price"), "as_of": prof.get("as_of"), "source": "Yahoo Finance quote"}


def _peer_list(ticker: str, requested: Optional[str]) -> Dict:
    if requested:
        peers = [p for p in (x.strip().upper() for x in requested.split(",")) if p and VALID_SYMBOL.match(p) and p != ticker]
        return {"tickers": peers[:6], "basis": "chosen by you"}
    try:  # competitors named with evidence in filings or news
        with _engine().connect() as conn:
            rows = conn.execute(text("SELECT DISTINCT partner_ticker FROM supply_chain WHERE ticker=:t AND relationship='COMPETITOR' "
                                     "AND status='active' AND COALESCE(source_type,'legacy') <> 'legacy' LIMIT 5"), {"t": ticker}).fetchall()
        tk = [r[0] for r in rows if r[0]]
        if tk:
            return {"tickers": tk, "basis": "competitors named in filings or news (evidence-backed)"}
    except Exception:
        pass
    return {"tickers": [], "basis": "none chosen — add the companies you want to compare against"}


def _ratios(items: Dict, price: Optional[float]) -> Dict:
    shares = items.get("diluted_shares")
    mcap = price * shares if price and shares else None
    r = fx.compute_ratios(items, mcap, price, items.get("dps"))
    r.pop("ev_ebitda", None)
    return r


def _company_facts(ticker: str) -> Dict:
    st = verified_statements(ticker)
    if not st["years"]:
        raise HTTPException(status_code=404, detail=f"No annual financial statements found for {ticker}.")
    mp = market_price(ticker)
    years = []
    for i, y in enumerate(st["years"]):
        years.append({**y, "ratios": _ratios(y["items"], mp["price"] if i == 0 else None)})
    return {"statements": st, "years": years, "market": mp}


def _history_stats(ticker: str) -> Dict:
    """Historical price statistics (facts about the past, not forecasts) from Yahoo daily prices."""
    px = get_prices([ticker, "SPY"], years=3)
    if px.empty or ticker not in px:
        return {}
    s = px[ticker].dropna()
    m = px["SPY"].dropna() if "SPY" in px else None
    rf = get_macro().get("ten_year_yield") or FALLBACK_RISK_FREE
    out = fx.risk_metrics(s, m, rf)
    out.pop("sharpe", None)
    out.pop("var_95_1d_parametric", None)
    out["window"] = {"start": str(s.index[0].date()), "end": str(s.index[-1].date())}
    out["source"] = "Yahoo Finance daily closes (split- and dividend-adjusted); beta and correlation vs SPY"
    out["chart"] = [{"date": str(d.date()), "price": float(v), "drawdown": float(v / s.loc[:d].max() - 1)} for d, v in s.iloc[::5].items()]
    return out


def _sources(ticker: str, st: Dict) -> List[Dict]:
    out = []
    if st.get("sec_source"):
        out.append({"label": f"SEC EDGAR — {ticker} XBRL financial data (as reported in annual filings)", "url": st["sec_source"]})
    out.append({"label": f"SEC EDGAR — {ticker} filings", "url": f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&ticker={ticker}&type=10-K"})
    out.append({"label": f"Yahoo Finance — {ticker} (prices; cross-check only)", "url": f"https://finance.yahoo.com/quote/{ticker}"})
    return out


# ======================================================================= endpoints
@router.get("/glossary")
def glossary():
    """Shared plain-language definitions, used for hover definitions in the UI (same text as explain.py)."""
    from app.internal.glossary import as_api
    return as_api()


@router.get("/watchlist/summary")
def watchlist_summary():
    """One row of reported facts per watchlist company. Follows the watchlist automatically."""
    from concurrent.futures import ThreadPoolExecutor

    def row(t):
        try:
            f = _company_facts(t)
            y = f["years"][0]
            prof = get_profile(t)
            return {"ticker": t, "name": prof.get("name"), "fiscal_year_end": y["fiscal_year_end"], "currency": f["statements"]["currency"],
                    "price": f["market"]["price"], "revenue": y["items"].get("revenue"), "net_income": y["items"].get("net_income"),
                    "net_margin": y["ratios"].get("net_margin"), "roe": y["ratios"].get("roe"), "debt_to_equity": y["ratios"].get("debt_to_equity"),
                    "pe": y["ratios"].get("pe"), "dividend_yield": y["ratios"].get("dividend_yield"),
                    "sec_coverage": f["statements"]["coverage"]}
        except HTTPException as e:
            return {"ticker": t, "error": e.detail}
        except Exception as e:
            return {"ticker": t, "error": str(e)[:200]}
    tickers = _active_watchlist()
    with ThreadPoolExecutor(max_workers=4) as pool:
        rows = list(pool.map(row, tickers))
    return {"tickers": tickers, "rows": rows}


@router.get("/{ticker}/report")
def company_report(ticker: str, peers: Optional[str] = None):
    t = _norm(ticker)
    try:
        f = _company_facts(t)
        prof = get_profile(t)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Could not load data for {t}: {e}")
    years, st = f["years"], f["statements"]

    peer_set = _peer_list(t, peers)
    peer_rows = []
    for p in peer_set["tickers"]:
        try:
            pf = _company_facts(p)
            peer_rows.append({"ticker": p, "name": get_profile(p).get("name"), "fiscal_year_end": pf["years"][0]["fiscal_year_end"],
                              "ratios": pf["years"][0]["ratios"], "revenue": pf["years"][0]["items"].get("revenue"),
                              "currency": pf["statements"]["currency"]})
        except Exception as e:
            peer_rows.append({"ticker": p, "ratios": {}, "error": str(getattr(e, "detail", e))[:160]})
    median = {k: fx.median_ignore_none(pr["ratios"].get(k) for pr in peer_rows) for k, *_ in RATIO_DEFS}

    growth = {}
    if len(years) >= 2:
        n = len(years) - 1
        for k in ("revenue", "net_income", "free_cash_flow", "eps_diluted"):
            growth[k] = fx.cagr(years[-1]["items"].get(k), years[0]["items"].get(k), n)
        growth["years"] = n

    dps = [{"year": y["fiscal_year_end"][:4], "dps": y["items"].get("dps")} for y in reversed(years) if y["items"].get("dps")]
    plain = None
    try:  # plain-language summary of the latest year, from templates (no AI)
        from app.internal import explain as X
        ex = X.Explainer()
        y0 = years[0]
        prev = years[1]["items"] if len(years) > 1 else None
        peer_names = ", ".join(pr["ticker"] for pr in peer_rows if not pr.get("error")) or "none chosen"
        plain = {"lead": X.financial_lead(prof.get("name") or t, y0["fiscal_year_end"], y0["items"], prev, st["currency"], ex),
                 "points": X.financial_points(y0["items"], y0["ratios"], median, peer_names, growth, st["currency"], ex,
                                              pe_note=f" and the {f['market'].get('source')} share price" if y0["ratios"].get("pe") else ""),
                 "means": X.means("financials")}
    except Exception as e:
        print(f"⚠️ plain summary failed for {t}: {e}")
    return {
        "plain": plain,
        "profile": {"ticker": t, "name": prof.get("name"), "sector": prof.get("sector"), "industry": prof.get("industry"),
                    "country": prof.get("country"), "summary": prof.get("summary"), "currency": st["currency"]},
        "market": f["market"],
        "years": years,
        "coverage": st["coverage"],
        "ratio_definitions": [{"key": k, "label": l, "group": g, "formula": fm, "unit": u} for k, l, g, fm, u in RATIO_DEFS],
        "growth": growth,
        "peers": {"basis": peer_set["basis"], "rows": peer_rows, "median": median},
        "dividends": {"annual": dps, "pays_dividend": bool(dps), "source": "dividends per share declared, as reported to the SEC"},
        "history": {k: v for k, v in _history_stats(t).items() if k != "chart"},
        "sources": _sources(t, st),
        "note": "Reported figures, market prices and standard ratio formulas. The rating on the Investment view tab comes from a fixed formula with listed assumptions; it is not personal advice.",
    }


@router.get("/{ticker}/history")
def price_history(ticker: str):
    t = _norm(ticker)
    h = _history_stats(t)
    if not h:
        raise HTTPException(status_code=404, detail=f"No price history for {t}.")
    return {"ticker": t, "metrics": h}


class PortfolioReq(BaseModel):
    tickers: List[str]
    weights: Optional[Dict[str, float]] = None
    budget: float = Field(100000, gt=0)
    years: int = Field(3, ge=1, le=10)


@router.get("/{ticker}/price-check")
def price_check(ticker: str, since: Optional[str] = None):
    """Facts that test common reasons to buy or sell: trend over standard periods, monthly ups/downs,
    distance from the 52-week high, volatility vs the S&P 500 and sector fund, and change since a date."""
    from app.internal.price_facts import price_check as pc
    out = pc(_norm(ticker), since)
    if "error" in out:
        raise HTTPException(status_code=404, detail=out["error"])
    return out


@router.get("/{ticker}/valuation")
def valuation(ticker: str):
    """Fair-value estimate and rule-based BUY / HOLD / SELL rating, with dividend policy and risk checks.
    Formula result with listed inputs and assumptions; not personal advice."""
    t = _norm(ticker)
    try:
        from app.internal.valuation import build
        return build(t)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Could not build the valuation for {t}: {e}")


@router.get("/{ticker}/model-portfolio")
def model_portfolio(ticker: str, budget: float = 100000):
    """The team report's diversified template portfolio with this stock as the 15% core holding."""
    t = _norm(ticker)
    if not 1000 <= budget <= 1e9:
        raise HTTPException(status_code=400, detail="Budget must be between $1,000 and $1 billion.")
    try:
        from app.internal.valuation import build_portfolio
        return build_portfolio(t, budget)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Could not build the model portfolio for {t}: {e}")


@router.post("/portfolio")
def portfolio(req: PortfolioReq):
    """Historical behaviour of a weighted basket. Describes the past only; no suggested weights."""
    tickers = list(dict.fromkeys(_norm(x) for x in req.tickers if x.strip()))
    if not 2 <= len(tickers) <= 25:
        raise HTTPException(status_code=400, detail="Pick between 2 and 25 tickers.")
    weights = {k.upper(): v for k, v in (req.weights or {}).items()} or {t: 1 / len(tickers) for t in tickers}
    for t in tickers:
        weights.setdefault(t, 0.0)
    px = get_prices(tickers, years=req.years)
    missing = [t for t in tickers if t not in px or px[t].dropna().empty]
    rf = get_macro().get("ten_year_yield") or FALLBACK_RISK_FREE
    res = fx.portfolio_analysis(px[[t for t in tickers if t not in missing]], weights, req.budget, rf)
    if "error" in res:
        raise HTTPException(status_code=400, detail=res["error"])
    res.pop("alternatives", None)
    res["missing"], res["budget"] = missing, req.budget
    res["method"] = ("Historical only: Yahoo Finance daily closes (split- and dividend-adjusted) over the window. "
                     "Return = annualised average daily return; volatility = annualised standard deviation; "
                     "portfolio volatility uses the full covariance matrix. Past performance is not a forecast.")
    return res
