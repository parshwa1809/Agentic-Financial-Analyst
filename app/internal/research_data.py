"""
Data access for the research module (Company Report, Risk, Portfolio Lab,
Project Evaluator, Report Validator).

Source: Yahoo Finance via `yfinance` (free, no key). Statement figures there are
taken from the company's SEC filings, so every number we show carries a link to
both the Yahoo page and the SEC filing index for the user to check against.

Results are cached in memory for a few hours so the UI stays fast and we stay
well inside Yahoo's informal rate limits.
"""
from __future__ import annotations

import threading
import time
from typing import Dict, List, Optional

import pandas as pd
import yfinance as yf

from app.internal.finance import clean

_CACHE: Dict[str, tuple] = {}
_LOCK = threading.Lock()
# yf.download keeps its results in a module-level dict, so two downloads running at once can hand each other's
# prices back (seen live: KO's year-end "prices" coming back as another ticker's). One download at a time.
_YF_LOCK = threading.Lock()
TTL_SECONDS = 6 * 3600


def cached(key: str, fn, ttl: int = TTL_SECONDS):
    now = time.time()
    with _LOCK:
        hit = _CACHE.get(key)
        if hit and now - hit[0] < ttl:
            return hit[1]
    value = fn()
    with _LOCK:
        _CACHE[key] = (now, value)
    return value


def sources_for(ticker: str) -> List[Dict[str, str]]:
    t = ticker.upper()
    return [
        {"label": f"Yahoo Finance — {t} financial statements", "url": f"https://finance.yahoo.com/quote/{t}/financials"},
        {"label": f"Yahoo Finance — {t} key statistics", "url": f"https://finance.yahoo.com/quote/{t}/key-statistics"},
        {"label": f"SEC EDGAR — {t} 10-K filings", "url": f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&ticker={t}&type=10-K"},
    ]


# Statement line items we use, with the alternative row names yfinance has used over versions.
LINE_ITEMS = {
    "revenue": ("income", ["Total Revenue", "Operating Revenue"]),
    "cost_of_revenue": ("income", ["Cost Of Revenue", "Reconciled Cost Of Revenue"]),
    "gross_profit": ("income", ["Gross Profit"]),
    "operating_income": ("income", ["Operating Income", "Total Operating Income As Reported"]),
    "ebitda": ("income", ["EBITDA", "Normalized EBITDA"]),
    "interest_expense": ("income", ["Interest Expense", "Interest Expense Non Operating"]),
    "pretax_income": ("income", ["Pretax Income"]),
    "tax_provision": ("income", ["Tax Provision"]),
    "net_income": ("income", ["Net Income", "Net Income Common Stockholders"]),
    "eps_diluted": ("income", ["Diluted EPS"]),
    "diluted_shares": ("income", ["Diluted Average Shares"]),
    "current_assets": ("balance", ["Current Assets"]),
    "current_liabilities": ("balance", ["Current Liabilities"]),
    "inventory": ("balance", ["Inventory"]),
    "cash": ("balance", ["Cash And Cash Equivalents", "Cash Cash Equivalents And Short Term Investments"]),
    "total_assets": ("balance", ["Total Assets"]),
    "total_liabilities": ("balance", ["Total Liabilities Net Minority Interest"]),
    "equity": ("balance", ["Stockholders Equity", "Common Stock Equity"]),
    "total_debt": ("balance", ["Total Debt"]),
    "operating_cash_flow": ("cashflow", ["Operating Cash Flow"]),
    "capex": ("cashflow", ["Capital Expenditure"]),
    "free_cash_flow": ("cashflow", ["Free Cash Flow"]),
    "dividends_paid": ("cashflow", ["Cash Dividends Paid", "Common Stock Dividend Paid"]),
    "buybacks": ("cashflow", ["Repurchase Of Capital Stock", "Common Stock Payments"]),
}


def _statements(ticker: str) -> Dict[str, pd.DataFrame]:
    t = yf.Ticker(ticker)
    return {"income": t.income_stmt, "balance": t.balance_sheet, "cashflow": t.cashflow}


def get_statements(ticker: str) -> List[Dict]:
    """Annual statement line items, newest fiscal year first.
    Each element: {"fiscal_year_end": "2024-12-31", "revenue": ..., ...}"""
    def load():
        st = _statements(ticker)
        cols = set()
        for df in st.values():
            if df is not None and not df.empty:
                cols.update(df.columns)
        years = sorted(cols, reverse=True)
        out = []
        for col in years:
            row: Dict[str, Optional[float]] = {"fiscal_year_end": str(pd.Timestamp(col).date())}
            for key, (sheet, names) in LINE_ITEMS.items():
                df = st.get(sheet)
                val = None
                if df is not None and not df.empty and col in df.columns:
                    for n in names:
                        if n in df.index:
                            val = clean(df.at[n, col])
                            if val is not None:
                                break
                row[key] = val
            # keep only years that actually have revenue (yfinance pads with empty columns)
            if row.get("revenue") is not None:
                out.append(row)
        return out[:5]
    return cached(f"stmts:{ticker}", load)


def get_profile(ticker: str) -> Dict:
    def load():
        t = yf.Ticker(ticker)
        info = t.info or {}
        price = clean(info.get("currentPrice") or info.get("regularMarketPrice") or info.get("previousClose"))
        return {
            "ticker": ticker.upper(),
            "name": info.get("longName") or info.get("shortName") or ticker.upper(),
            "sector": info.get("sector"), "industry": info.get("industry"),
            "country": info.get("country"), "employees": info.get("fullTimeEmployees"),
            "summary": info.get("longBusinessSummary"),
            "currency": info.get("currency", "USD"),
            "financial_currency": info.get("financialCurrency"),
            "price": price,
            "market_cap": clean(info.get("marketCap")),
            "shares_outstanding": clean(info.get("sharesOutstanding")),
            "beta_yahoo": clean(info.get("beta")),
            "fifty_two_week_high": clean(info.get("fiftyTwoWeekHigh")),
            "fifty_two_week_low": clean(info.get("fiftyTwoWeekLow")),
            "analyst_target_mean": clean(info.get("targetMeanPrice")),
            "analyst_recommendation": info.get("recommendationKey"),
            "analyst_count": info.get("numberOfAnalystOpinions"),
            "forward_eps": clean(info.get("forwardEps")),
            "as_of": time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime()),
        }
    return cached(f"profile:{ticker}", load, ttl=3600)


def get_dividends(ticker: str) -> Dict:
    """Dividend history from actual payments: annual DPS, TTM DPS and growth."""
    def load():
        s = yf.Ticker(ticker).dividends
        if s is None or s.empty:
            return {"annual": [], "ttm_dps": None, "pays_dividend": False}
        s.index = pd.to_datetime(s.index).tz_localize(None)
        annual = s.groupby(s.index.year).sum()
        this_year = pd.Timestamp.now().year
        annual_full = annual[annual.index < this_year].tail(10)
        cutoff = pd.Timestamp.now() - pd.Timedelta(days=365)
        ttm = float(s[s.index > cutoff].sum())
        last = s.index.max()
        return {
            "pays_dividend": True,
            "annual": [{"year": int(y), "dps": float(v)} for y, v in annual_full.items()],
            "ttm_dps": ttm,
            "last_payment": {"date": str(last.date()), "amount": float(s.iloc[-1])},
            "consecutive_increase_years": _streak(annual_full),
        }
    return cached(f"divs:{ticker}", load)


def _streak(annual: pd.Series) -> int:
    vals = list(annual.values)
    n = 0
    for i in range(len(vals) - 1, 0, -1):
        if vals[i] > vals[i - 1]:
            n += 1
        else:
            break
    return n


def get_prices(tickers: List[str], years: int = 3) -> pd.DataFrame:
    """Daily adjusted closes, one column per ticker."""
    key = f"px:{','.join(sorted(tickers))}:{years}"

    def load():
        with _YF_LOCK:
            df = yf.download(tickers, period=f"{years}y", interval="1d", auto_adjust=True, progress=False, threads=True)
        if df is None or df.empty:
            return pd.DataFrame()
        closes = df["Close"] if isinstance(df.columns, pd.MultiIndex) else df[["Close"]].rename(columns={"Close": tickers[0]})
        if isinstance(closes, pd.Series):
            closes = closes.to_frame(tickers[0])
        closes.index = pd.to_datetime(closes.index).tz_localize(None)
        return closes
    return cached(key, load, ttl=3600)


def get_closes(ticker: str, years: int = 6) -> pd.Series:
    """Daily closing prices adjusted for splits but NOT for dividends: the price people actually paid on that day.
    Used for historical P/E (get_prices() is dividend-adjusted, which would understate old prices)."""
    def load():
        with _YF_LOCK:
            df = yf.download([ticker], period=f"{years}y", interval="1d", auto_adjust=False, progress=False, threads=False)
        if df is None or df.empty:
            return pd.Series(dtype=float)
        if isinstance(df.columns, pd.MultiIndex) and ticker not in df.columns.get_level_values(-1):
            raise ValueError(f"price download for {ticker} returned another symbol's data")
        c = df["Close"]
        if isinstance(c, pd.DataFrame):
            c = c.iloc[:, 0]
        c.index = pd.to_datetime(c.index).tz_localize(None)
        return c.dropna()
    return cached(f"closes:{ticker}:{years}", load, ttl=6 * 3600)


def get_macro() -> Dict:
    """Market backdrop: 10-year Treasury yield, S&P 500 and US dollar index."""
    def load():
        px = get_prices(["^TNX", "^GSPC", "DX-Y.NYB"], years=1)
        out = {"sources": [
            {"label": "Yahoo Finance — ^TNX (10-yr Treasury yield)", "url": "https://finance.yahoo.com/quote/%5ETNX"},
            {"label": "Yahoo Finance — ^GSPC (S&P 500)", "url": "https://finance.yahoo.com/quote/%5EGSPC"},
            {"label": "Yahoo Finance — DX-Y.NYB (US dollar index)", "url": "https://finance.yahoo.com/quote/DX-Y.NYB"},
        ]}
        if "^TNX" in px and px["^TNX"].dropna().size:
            tnx = px["^TNX"].dropna()
            out["ten_year_yield"] = float(tnx.iloc[-1]) / 100.0
            out["ten_year_yield_change_1y"] = (float(tnx.iloc[-1]) - float(tnx.iloc[0])) / 100.0
        for sym, key in (("^GSPC", "sp500_return_1y"), ("DX-Y.NYB", "usd_index_change_1y")):
            if sym in px and px[sym].dropna().size > 1:
                s = px[sym].dropna()
                out[key] = float(s.iloc[-1] / s.iloc[0] - 1)
        out["as_of"] = str(px.index.max().date()) if not px.empty else None
        return out
    return cached("macro", load, ttl=3600)
