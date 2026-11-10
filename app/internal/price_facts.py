"""
Price facts for checking a reason to buy or sell ("it's volatile", "it keeps going down").

Everything here is arithmetic on daily closing prices (Yahoo Finance, split- and dividend-adjusted),
compared with the S&P 500 (SPY) and the stock's sector fund (SPDR Select Sector ETF). It describes
what HAS happened. It does not say whether a decision was right: that depends on the person's goals,
time horizon, taxes and what they did with the money, which the data can't know.
"""
from datetime import date, datetime
from typing import Dict, Optional

import pandas as pd

from app.internal.research_data import get_prices, get_profile

SECTOR_ETF = {"Technology": "XLK", "Financial Services": "XLF", "Healthcare": "XLV", "Consumer Defensive": "XLP",
              "Consumer Cyclical": "XLY", "Energy": "XLE", "Industrials": "XLI", "Basic Materials": "XLB",
              "Utilities": "XLU", "Real Estate": "XLRE", "Communication Services": "XLC"}
PERIODS = [("1 week", 5), ("1 month", 21), ("3 months", 63), ("6 months", 126), ("1 year", 252), ("3 years", None)]
DAYS = 252


def _ret(s: pd.Series, n: Optional[int]):
    s = s.dropna()
    if len(s) < 2 or (n and len(s) <= n):
        return None
    return float(s.iloc[-1] / (s.iloc[0] if n is None else s.iloc[-1 - n]) - 1)


def _vol(s: pd.Series, n: int):
    r = s.dropna().pct_change().dropna().iloc[-n:]
    return float(r.std() * DAYS ** 0.5) if len(r) > 20 else None


def price_check(ticker: str, since: Optional[str] = None) -> Dict:
    t = ticker.upper()
    prof = get_profile(t)
    sector = prof.get("sector")
    etf = SECTOR_ETF.get(sector)
    cols = [t, "SPY"] + ([etf] if etf else [])
    px = get_prices(cols, years=3)
    if px.empty or t not in px or px[t].dropna().empty:
        return {"error": f"No price history for {t}."}
    s, spy = px[t].dropna(), px["SPY"].dropna()
    sec = px[etf].dropna() if etf and etf in px else None
    bench = {"S&P 500 (SPY)": spy, **({f"{sector} sector ({etf})": sec} if sec is not None else {})}

    periods = []
    for label, n in PERIODS:
        row = {"period": label, t: _ret(s, n)}
        row.update({k: _ret(v, n) for k, v in bench.items()})
        periods.append(row)
    ytd = s[s.index >= pd.Timestamp(date.today().year, 1, 1)]
    if len(ytd) > 1:
        row = {"period": "Year to date", t: float(s.iloc[-1] / ytd.iloc[0] - 1)}
        for k, v in bench.items():
            vy = v[v.index >= pd.Timestamp(date.today().year, 1, 1)]
            row[k] = float(v.iloc[-1] / vy.iloc[0] - 1) if len(vy) > 1 else None
        periods.insert(4, row)

    try:
        monthly = s.resample("ME").last()
    except ValueError:  # pandas < 2.2
        monthly = s.resample("M").last()
    monthly = monthly.pct_change().dropna().iloc[-12:]
    months = [{"month": d.strftime("%Y-%m"), "return": float(v)} for d, v in monthly.items()]
    last_year = s.iloc[-DAYS:]
    hi_d = last_year.idxmax()
    lo_d = last_year.idxmin()
    dd = float((last_year / last_year.cummax() - 1).min())

    vol = {t: _vol(s, DAYS), **{k: _vol(v, DAYS) for k, v in bench.items()}}
    vol3m = {t: _vol(s, 63), **{k: _vol(v, 63) for k, v in bench.items()}}

    out = {
        "ticker": t, "name": prof.get("name") or t, "sector": sector, "as_of": str(s.index[-1].date()), "price": float(s.iloc[-1]),
        "benchmarks": list(bench.keys()), "periods": periods, "months": months,
        "up_months": sum(1 for m in months if m["return"] > 0), "down_months": sum(1 for m in months if m["return"] <= 0),
        "high_52w": {"price": float(last_year.max()), "date": str(hi_d.date())},
        "low_52w": {"price": float(last_year.min()), "date": str(lo_d.date())},
        "below_high": float(s.iloc[-1] / last_year.max() - 1),
        "largest_fall_1y": dd,
        "volatility_1y": vol, "volatility_3m": vol3m,
        "source": "Yahoo Finance daily closes (split- and dividend-adjusted); benchmarks SPY and the SPDR sector ETF",
    }
    if since:
        try:
            d0 = pd.Timestamp(datetime.fromisoformat(since[:10]))
            after = s[s.index >= d0]
            if len(after) > 0:
                p0 = float(after.iloc[0])
                row = {"date": str(after.index[0].date()), "price_then": p0, "price_now": float(s.iloc[-1]),
                       "change": float(s.iloc[-1] / p0 - 1)}
                for k, v in bench.items():
                    va = v[v.index >= d0]
                    row[k] = float(v.iloc[-1] / va.iloc[0] - 1) if len(va) else None
                out["since"] = row
        except ValueError:
            pass
    out["checks"] = _checks(out)
    return out


def _checks(d: Dict) -> list:
    """Each common reason, tested with the numbers, in plain words (see app/internal/explain.py).
    Wording states facts and comparisons, never a verdict on the decision."""
    from app.internal.explain import claim_story
    st = claim_story(d)
    d["story"] = st
    out = [{"claim": "It is highly volatile", "facts": st["swings"]}, {"claim": "It keeps going down", "facts": st["direction"]}]
    if st["since"]:
        out.append({"claim": f"Since {d['since']['date']}", "facts": st["since"]})
    return out
