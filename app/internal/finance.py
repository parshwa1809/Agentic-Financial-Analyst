"""
Pure financial math for Project Oracle's research module.

Everything here is deterministic: given the same inputs it returns the same
numbers, and every function documents its formula so a result can be checked
by hand. No network calls and no LLMs live in this file.
"""
from __future__ import annotations

import math
from typing import Dict, Iterable, List, Optional, Sequence

import numpy as np
import pandas as pd

TRADING_DAYS = 252


# ----------------------------------------------------------------- helpers
def safe_div(a: Optional[float], b: Optional[float]) -> Optional[float]:
    """a / b, or None when either side is missing or b is zero."""
    try:
        if a is None or b is None:
            return None
        a, b = float(a), float(b)
        if math.isnan(a) or math.isnan(b) or b == 0:
            return None
        return a / b
    except (TypeError, ValueError):
        return None


def clean(x) -> Optional[float]:
    """Convert numpy / pandas scalars to a JSON-safe float (or None)."""
    try:
        if x is None:
            return None
        f = float(x)
        return None if (math.isnan(f) or math.isinf(f)) else f
    except (TypeError, ValueError):
        return None


def cagr(first: Optional[float], last: Optional[float], years: float) -> Optional[float]:
    """Compound annual growth rate = (last / first) ** (1 / years) - 1."""
    if first is None or last is None or years <= 0 or first <= 0 or last <= 0:
        return None
    return (last / first) ** (1.0 / years) - 1.0


# ----------------------------------------------------------------- capital budgeting
def npv(rate: float, cash_flows: Sequence[float]) -> float:
    """NPV = sum(CF_t / (1 + r)^t), t = 0..n. CF_0 is usually the (negative) investment."""
    return float(sum(cf / (1.0 + rate) ** t for t, cf in enumerate(cash_flows)))


def irr(cash_flows: Sequence[float], lo: float = -0.99, hi: float = 10.0, tol: float = 1e-7) -> Optional[float]:
    """Internal rate of return: the rate where NPV = 0 (bisection, so it always converges
    when a sign change exists). Returns None if NPV never crosses zero in [lo, hi]."""
    f_lo, f_hi = npv(lo, cash_flows), npv(hi, cash_flows)
    if f_lo * f_hi > 0:
        return None
    for _ in range(300):
        mid = (lo + hi) / 2.0
        f_mid = npv(mid, cash_flows)
        if abs(f_mid) < tol:
            return mid
        if f_lo * f_mid < 0:
            hi, f_hi = mid, f_mid
        else:
            lo, f_lo = mid, f_mid
    return (lo + hi) / 2.0


def payback_period(cash_flows: Sequence[float]) -> Optional[float]:
    """Years until cumulative (undiscounted) cash flow turns non-negative, with linear
    interpolation inside the year it happens. None if it never pays back."""
    cum = 0.0
    for t, cf in enumerate(cash_flows):
        prev = cum
        cum += cf
        if t > 0 and cum >= 0 and prev < 0:
            return (t - 1) + (-prev / cf if cf else 0.0)
    return 0.0 if cash_flows and cash_flows[0] >= 0 else None


def discounted_payback(rate: float, cash_flows: Sequence[float]) -> Optional[float]:
    """Payback period computed on discounted cash flows CF_t / (1 + r)^t."""
    return payback_period([cf / (1.0 + rate) ** t for t, cf in enumerate(cash_flows)])


def profitability_index(rate: float, cash_flows: Sequence[float]) -> Optional[float]:
    """PI = PV(future cash flows) / |initial investment|."""
    if not cash_flows or cash_flows[0] >= 0:
        return None
    pv_future = npv(rate, [0.0] + list(cash_flows[1:]))
    return pv_future / abs(cash_flows[0])


def capm_cost_of_equity(risk_free: float, beta: float, market_premium: float) -> float:
    """CAPM: r_e = r_f + beta * (E[R_m] - r_f)."""
    return risk_free + beta * market_premium


def wacc(equity_value: float, debt_value: float, cost_equity: float, cost_debt: float, tax_rate: float) -> Optional[float]:
    """WACC = E/V * r_e + D/V * r_d * (1 - t)."""
    v = (equity_value or 0) + (debt_value or 0)
    if v <= 0:
        return None
    return (equity_value / v) * cost_equity + (debt_value / v) * cost_debt * (1.0 - tax_rate)


def evaluate_project(cash_flows: Sequence[float], rate: float) -> Dict:
    """Full capital-budgeting read-out plus a sensitivity grid."""
    flows = [float(x) for x in cash_flows]
    base = {
        "npv": npv(rate, flows),
        "irr": irr(flows),
        "payback_years": payback_period(flows),
        "discounted_payback_years": discounted_payback(rate, flows),
        "profitability_index": profitability_index(rate, flows),
        "discount_rate": rate,
    }
    rates = [round(rate + d, 4) for d in (-0.02, -0.01, 0.0, 0.01, 0.02)]
    cf_shocks = [-0.2, -0.1, 0.0, 0.1, 0.2]
    grid = []
    for shock in cf_shocks:
        shocked = [flows[0]] + [cf * (1 + shock) for cf in flows[1:]]
        grid.append({"cash_flow_change": shock, "npv": [npv(r, shocked) for r in rates]})
    pv_rows = [{"year": t, "cash_flow": cf, "discount_factor": 1 / (1 + rate) ** t,
                "present_value": cf / (1 + rate) ** t,
                "cumulative": float(sum(flows[: t + 1]))} for t, cf in enumerate(flows)]
    base["schedule"] = pv_rows
    base["sensitivity"] = {"rates": rates, "rows": grid}
    base["decision"] = ("Accept — NPV is positive, so the project earns more than its cost of capital"
                        if base["npv"] > 0 else
                        "Reject — NPV is negative, so the project earns less than its cost of capital")
    return base


# ----------------------------------------------------------------- risk
def daily_returns(prices: pd.Series) -> pd.Series:
    return prices.sort_index().pct_change().dropna()


def max_drawdown(prices: pd.Series) -> Optional[float]:
    """Largest peak-to-trough fall: min(P_t / max(P_0..P_t) - 1)."""
    if prices is None or len(prices) < 2:
        return None
    p = prices.sort_index()
    return float((p / p.cummax() - 1.0).min())


def risk_metrics(prices: pd.Series, market: Optional[pd.Series], risk_free: float) -> Dict:
    """Annualised return/volatility, beta vs the market, Sharpe, drawdown and 1-day VaR."""
    r = daily_returns(prices)
    if len(r) < 30:
        return {}
    ann_ret = float((1 + r).prod() ** (TRADING_DAYS / len(r)) - 1)
    ann_vol = float(r.std() * math.sqrt(TRADING_DAYS))
    out = {
        "observations": int(len(r)),
        "annual_return": ann_ret,
        "annual_volatility": ann_vol,
        "sharpe": safe_div(ann_ret - risk_free, ann_vol),
        "max_drawdown": max_drawdown(prices),
        "var_95_1d_historical": float(-np.percentile(r, 5)),
        "var_95_1d_parametric": float(-(r.mean() - 1.645 * r.std())),
        "worst_day": float(r.min()),
        "best_day": float(r.max()),
    }
    if market is not None and len(market) > 30:
        m = daily_returns(market)
        joined = pd.concat([r, m], axis=1, join="inner").dropna()
        if len(joined) > 30:
            cov = np.cov(joined.iloc[:, 0], joined.iloc[:, 1])
            out["beta"] = float(cov[0, 1] / cov[1, 1])
            out["correlation_to_market"] = float(joined.corr().iloc[0, 1])
    return out


# ----------------------------------------------------------------- portfolio
def portfolio_analysis(prices: pd.DataFrame, weights: Dict[str, float], budget: float, risk_free: float) -> Dict:
    """Risk/return of a weighted portfolio plus two benchmark weightings.

    expected return  = w · mu            (mu = annualised mean daily return)
    volatility       = sqrt(w' Σ w)      (Σ = annualised covariance of daily returns)
    """
    prices = prices.sort_index().dropna(how="all").ffill().dropna()
    rets = prices.pct_change().dropna()
    cols = [c for c in rets.columns if c in weights]
    if len(cols) < 1 or len(rets) < 30:
        return {"error": "Not enough overlapping price history for these tickers."}
    rets = rets[cols]
    mu = rets.mean() * TRADING_DAYS
    cov = rets.cov() * TRADING_DAYS
    vols = np.sqrt(np.diag(cov))

    def stats(w: np.ndarray) -> Dict:
        er = float(w @ mu.values)
        vol = float(math.sqrt(max(w @ cov.values @ w, 0)))
        return {"expected_return": er, "volatility": vol, "sharpe": safe_div(er - risk_free, vol)}

    w_user = np.array([max(float(weights[c]), 0.0) for c in cols])
    w_user = w_user / w_user.sum() if w_user.sum() > 0 else np.ones(len(cols)) / len(cols)
    w_equal = np.ones(len(cols)) / len(cols)
    inv = 1.0 / np.where(vols > 0, vols, np.nan)
    w_invvol = np.nan_to_num(inv / np.nansum(inv))
    w_minvar = _min_variance(cov.values)

    weighted_avg_vol = float(w_user @ vols)
    port_vol = stats(w_user)["volatility"]
    holdings = []
    for i, c in enumerate(cols):
        price = float(prices[c].iloc[-1])
        alloc = budget * w_user[i]
        holdings.append({
            "ticker": c, "weight": float(w_user[i]), "allocation": alloc, "last_price": price,
            "shares": math.floor(alloc / price) if price > 0 else 0,
            "annual_return": float(mu[c]), "annual_volatility": float(vols[i]),
            "risk_contribution": float(w_user[i] * (cov.values @ w_user)[i] / (port_vol ** 2)) if port_vol > 0 else None,
        })
    return {
        "tickers": cols,
        "observations": int(len(rets)),
        "start": str(rets.index[0].date()), "end": str(rets.index[-1].date()),
        "holdings": holdings,
        "portfolio": stats(w_user),
        "diversification_ratio": safe_div(weighted_avg_vol, port_vol),
        "alternatives": {
            "equal_weight": {"weights": dict(zip(cols, map(float, w_equal))), **stats(w_equal)},
            "inverse_volatility": {"weights": dict(zip(cols, map(float, w_invvol))), **stats(w_invvol)},
            "minimum_variance": {"weights": dict(zip(cols, map(float, w_minvar))), **stats(w_minvar)},
        },
        "correlation": {"tickers": cols, "matrix": rets.corr().round(4).values.tolist()},
    }


def _min_variance(cov: np.ndarray, iters: int = 2000) -> np.ndarray:
    """Long-only minimum-variance weights via projected gradient descent on the simplex."""
    n = cov.shape[0]
    w = np.ones(n) / n
    step = 1.0 / (np.linalg.norm(cov, 2) + 1e-12)
    for _ in range(iters):
        w = _project_simplex(w - step * 2 * cov @ w)
    return w


def _project_simplex(v: np.ndarray) -> np.ndarray:
    """Euclidean projection onto {w >= 0, sum w = 1}."""
    u = np.sort(v)[::-1]
    css = np.cumsum(u)
    rho = np.nonzero(u * np.arange(1, len(v) + 1) > (css - 1))[0][-1]
    theta = (css[rho] - 1) / (rho + 1.0)
    return np.maximum(v - theta, 0)


# ----------------------------------------------------------------- ratios
RATIO_DEFS = [
    # key, label, group, formula text, unit
    ("current_ratio", "Current ratio", "Liquidity", "Current assets ÷ current liabilities", "x"),
    ("quick_ratio", "Quick ratio", "Liquidity", "(Current assets − inventory) ÷ current liabilities", "x"),
    ("cash_ratio", "Cash ratio", "Liquidity", "Cash & equivalents ÷ current liabilities", "x"),
    ("gross_margin", "Gross margin", "Profitability", "Gross profit ÷ revenue", "%"),
    ("operating_margin", "Operating margin", "Profitability", "Operating income ÷ revenue", "%"),
    ("net_margin", "Net margin", "Profitability", "Net income ÷ revenue", "%"),
    ("roe", "Return on equity", "Profitability", "Net income ÷ shareholders' equity", "%"),
    ("roa", "Return on assets", "Profitability", "Net income ÷ total assets", "%"),
    ("debt_to_equity", "Debt / equity", "Leverage", "Total debt ÷ shareholders' equity", "x"),
    ("debt_to_assets", "Debt / assets", "Leverage", "Total debt ÷ total assets", "x"),
    ("interest_coverage", "Interest coverage", "Leverage", "Operating income ÷ interest expense", "x"),
    ("asset_turnover", "Asset turnover", "Efficiency", "Revenue ÷ total assets", "x"),
    ("inventory_turnover", "Inventory turnover", "Efficiency", "Cost of revenue ÷ inventory", "x"),
    ("fcf_margin", "Free-cash-flow margin", "Cash flow", "Free cash flow ÷ revenue", "%"),
    ("pe", "P/E", "Valuation", "Current share price ÷ diluted EPS (latest fiscal year)", "x"),
    ("pb", "P/B", "Valuation", "Market cap ÷ shareholders' equity", "x"),
    ("ev_ebitda", "EV / EBITDA", "Valuation", "(Market cap + debt − cash) ÷ EBITDA", "x"),
    ("dividend_yield", "Dividend yield", "Dividends", "Dividends per share (latest fiscal year, SEC) ÷ current share price", "%"),
    ("payout_ratio", "Payout ratio", "Dividends", "Dividends paid ÷ net income", "%"),
]


def compute_ratios(y: Dict[str, Optional[float]], market_cap: Optional[float], price: Optional[float],
                   dps_ttm: Optional[float]) -> Dict[str, Optional[float]]:
    """Ratios for one fiscal year `y` (a dict of statement line items)."""
    debt = y.get("total_debt")
    cash = y.get("cash")
    ebitda = y.get("ebitda")
    interest = y.get("interest_expense")
    dividends_paid = y.get("dividends_paid")
    return {
        "current_ratio": safe_div(y.get("current_assets"), y.get("current_liabilities")),
        "quick_ratio": safe_div((y.get("current_assets") or 0) - (y.get("inventory") or 0), y.get("current_liabilities"))
        if y.get("current_assets") is not None else None,
        "cash_ratio": safe_div(cash, y.get("current_liabilities")),
        "gross_margin": safe_div(y.get("gross_profit"), y.get("revenue")),
        "operating_margin": safe_div(y.get("operating_income"), y.get("revenue")),
        "net_margin": safe_div(y.get("net_income"), y.get("revenue")),
        "roe": safe_div(y.get("net_income"), y.get("equity")),
        "roa": safe_div(y.get("net_income"), y.get("total_assets")),
        "debt_to_equity": safe_div(debt, y.get("equity")),
        "debt_to_assets": safe_div(debt, y.get("total_assets")),
        "interest_coverage": safe_div(y.get("operating_income"), abs(interest) if interest else None),
        "asset_turnover": safe_div(y.get("revenue"), y.get("total_assets")),
        "inventory_turnover": safe_div(y.get("cost_of_revenue"), y.get("inventory")),
        "fcf_margin": safe_div(y.get("free_cash_flow"), y.get("revenue")),
        "pe": safe_div(price, y.get("eps_diluted")) if price else None,
        "pb": safe_div(market_cap, y.get("equity")) if market_cap else None,
        "ev_ebitda": safe_div((market_cap or 0) + (debt or 0) - (cash or 0), ebitda) if market_cap else None,
        "dividend_yield": safe_div(dps_ttm, price) if dps_ttm is not None and price else None,
        "payout_ratio": safe_div(abs(dividends_paid) if dividends_paid else None, y.get("net_income")),
    }


def median_ignore_none(values: Iterable[Optional[float]]) -> Optional[float]:
    vals = [v for v in values if v is not None]
    return float(np.median(vals)) if vals else None


# ----------------------------------------------------------------- DCF valuation
def dcf_value(revenue0: float, fcf_margin: float, growth: float, years: int, wacc: float, terminal_growth: float,
              net_debt: float, shares: float) -> Dict:
    """Two-stage free-cash-flow DCF.

    Revenue_t = Revenue_0 × (1 + g)^t,  FCF_t = Revenue_t × margin
    TV = FCF_N × (1 + g_T) / (WACC − g_T),  EV = Σ FCF_t/(1+WACC)^t + TV/(1+WACC)^N
    Equity = EV − net debt,  value per share = Equity / diluted shares
    """
    if wacc <= terminal_growth:
        return {"error": "WACC must be above terminal growth"}
    rows, pv_sum = [], 0.0
    for t in range(1, years + 1):
        rev = revenue0 * (1 + growth) ** t
        fcf = rev * fcf_margin
        df = 1 / (1 + wacc) ** t
        pv_sum += fcf * df
        rows.append({"t": t, "revenue": rev, "fcf": fcf, "discount_factor": df, "present_value": fcf * df})
    tv = rows[-1]["fcf"] * (1 + terminal_growth) / (wacc - terminal_growth)
    tv_pv = tv / (1 + wacc) ** years
    ev = pv_sum + tv_pv
    equity = ev - (net_debt or 0)
    return {"projection": rows, "terminal": {"value": tv, "present_value": tv_pv, "share_of_ev": safe_div(tv_pv, ev)},
            "enterprise_value": ev, "equity_value": equity, "per_share": safe_div(equity, shares)}
