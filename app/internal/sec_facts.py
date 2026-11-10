"""
Official financial statements from SEC EDGAR's XBRL "company facts" API.

Every figure here is exactly what the company reported to the SEC in its annual report
(10-K, or 20-F / 40-F for foreign filers), tagged with US-GAAP or IFRS concepts. Each value
carries the form, fiscal year, filing date and accession number, so it can be traced to the
filing. Free, no key; the SEC only asks for a User-Agent with contact details (SEC_USER_AGENT).
"""
from datetime import date
from typing import Dict, List, Optional

from app.internal.research_data import cached

# Our line item → candidate XBRL concepts, in priority order (US-GAAP first, then IFRS).
CONCEPTS: Dict[str, List[str]] = {
    "revenue": ["us-gaap:Revenues", "us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax", "us-gaap:SalesRevenueNet",
                "ifrs-full:Revenue"],
    "cost_of_revenue": ["us-gaap:CostOfRevenue", "us-gaap:CostOfGoodsAndServicesSold", "ifrs-full:CostOfSales"],
    "gross_profit": ["us-gaap:GrossProfit", "ifrs-full:GrossProfit"],
    "operating_income": ["us-gaap:OperatingIncomeLoss", "ifrs-full:ProfitLossFromOperatingActivities"],
    "net_income": ["us-gaap:NetIncomeLoss", "ifrs-full:ProfitLossAttributableToOwnersOfParent", "ifrs-full:ProfitLoss"],
    "eps_diluted": ["us-gaap:EarningsPerShareDiluted", "ifrs-full:DilutedEarningsLossPerShare"],
    "interest_expense": ["us-gaap:InterestExpense", "us-gaap:InterestExpenseNonoperating", "us-gaap:InterestExpenseDebt",
                         "ifrs-full:FinanceCosts"],
    "total_assets": ["us-gaap:Assets", "ifrs-full:Assets"],
    "liabilities_and_equity": ["us-gaap:LiabilitiesAndStockholdersEquity", "ifrs-full:EquityAndLiabilities"],
    "liabilities": ["us-gaap:Liabilities", "ifrs-full:Liabilities"],
    "current_assets": ["us-gaap:AssetsCurrent", "ifrs-full:CurrentAssets"],
    "current_liabilities": ["us-gaap:LiabilitiesCurrent", "ifrs-full:CurrentLiabilities"],
    "cash": ["us-gaap:CashAndCashEquivalentsAtCarryingValue", "ifrs-full:CashAndCashEquivalents"],
    "inventory": ["us-gaap:InventoryNet", "ifrs-full:Inventories"],
    "equity": ["us-gaap:StockholdersEquity", "ifrs-full:EquityAttributableToOwnersOfParent"],
    "long_term_debt": ["us-gaap:LongTermDebtNoncurrent", "us-gaap:LongTermDebt", "ifrs-full:NoncurrentPortionOfNoncurrentBorrowings"],
    "short_term_debt": ["us-gaap:LongTermDebtCurrent", "us-gaap:DebtCurrent", "us-gaap:ShortTermBorrowings",
                        "ifrs-full:CurrentPortionOfNoncurrentBorrowings"],
    "operating_cash_flow": ["us-gaap:NetCashProvidedByUsedInOperatingActivities", "ifrs-full:CashFlowsFromUsedInOperatingActivities"],
    "capex": ["us-gaap:PaymentsToAcquirePropertyPlantAndEquipment",
              "ifrs-full:PurchaseOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities"],
    "dividends_paid": ["us-gaap:PaymentsOfDividendsCommonStock", "us-gaap:PaymentsOfDividends",
                       "ifrs-full:DividendsPaidClassifiedAsFinancingActivities"],
    "diluted_shares": ["us-gaap:WeightedAverageNumberOfDilutedSharesOutstanding",
                       "ifrs-full:AdjustedWeightedAverageShares"],
    "dps": ["us-gaap:CommonStockDividendsPerShareDeclared", "us-gaap:CommonStockDividendsPerShareCashPaid"],
}
FLOW = {"revenue", "cost_of_revenue", "gross_profit", "operating_income", "net_income", "eps_diluted", "interest_expense",
        "operating_cash_flow", "capex", "dividends_paid", "diluted_shares", "dps"}
ANNUAL_FORMS = {"10-K", "10-K/A", "20-F", "20-F/A", "40-F"}


def _facts(ticker: str) -> Optional[dict]:
    from services.sec_filings import _get, company_tickers
    info = company_tickers().get(ticker.upper())
    if not info:
        return None

    def load():
        js = _get(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{info['cik']:010d}.json", timeout=60).json()
        js["_cik"] = info["cik"]
        return js
    return cached(f"secfacts:{ticker.upper()}", load, ttl=12 * 3600)


def _pick(units: dict, key: str, prefer_currency: Optional[str]):
    """Choose the unit list (USD, or the reporting currency, or USD/shares for EPS)."""
    if key in ("eps_diluted", "dps"):
        for u in units:
            if "/shares" in u:
                return u, units[u]
    if key == "diluted_shares":
        return ("shares", units["shares"]) if "shares" in units else (None, None)
    if prefer_currency and prefer_currency in units:
        return prefer_currency, units[prefer_currency]
    if "USD" in units:
        return "USD", units["USD"]
    for u, v in units.items():
        if "/" not in u and u != "shares":
            return u, v
    return None, None


def annual_statements(ticker: str, years: int = 5) -> Dict:
    """{fiscal_year_end: {item: {"value", "unit", "concept", "form", "filed", "accn", "url"}}} newest first,
    plus "currency". Only annual-report values (10-K/20-F/40-F), full-year periods for flow items."""
    js = _facts(ticker)
    if not js:
        return {"years": {}, "currency": None, "cik": None}
    cik = js["_cik"]
    facts = js.get("facts", {})
    out: Dict[str, Dict] = {}
    currency = None
    for key, concepts in CONCEPTS.items():
        # Companies switch concepts over time (e.g. Revenues → RevenueFromContractWithCustomer…), so we
        # look through all candidates and, per fiscal year, keep the highest-priority concept that has it.
        for rank, c in enumerate(concepts):
            ns, name = c.split(":")
            node = facts.get(ns, {}).get(name)
            if not node:
                continue
            unit, rows = _pick(node.get("units", {}), key, currency)
            if not rows:
                continue
            if key == "revenue" and currency is None:
                currency = unit
            for row in rows:
                if row.get("form") not in ANNUAL_FORMS or row.get("fp") not in ("FY", None):
                    continue
                end = row.get("end")
                if key in FLOW:
                    start = row.get("start")
                    if not start or (date.fromisoformat(end) - date.fromisoformat(start)).days < 330:
                        continue
                prev = out.get(end, {}).get(key)
                if prev and (prev["rank"] < rank or (prev["rank"] == rank and prev["filed"] >= row.get("filed", ""))):
                    continue  # higher-priority concept already set, or a later filing (restatement) wins
                accn = row.get("accn", "")
                out.setdefault(end, {})[key] = {
                    "value": float(row["val"]), "unit": unit, "concept": c, "form": row.get("form"), "filed": row.get("filed", ""),
                    "accn": accn, "rank": rank,
                    "url": f"https://www.sec.gov/Archives/edgar/data/{cik}/{accn.replace('-', '')}/",
                }
    ends = sorted((e for e, v in out.items() if "revenue" in v or "net_income" in v), reverse=True)[:years]
    return {"years": {e: out[e] for e in ends}, "currency": currency, "cik": cik,
            "source": f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json"}
