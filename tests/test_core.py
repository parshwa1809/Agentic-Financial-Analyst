"""Fast unit tests for Oracle's deterministic core. No network, DB, Redis or LLM needed.

Run:  python -m unittest discover -s tests -v      (or inside Docker: docker compose exec api python -m unittest discover -s tests)
"""
import os
import sys
import types
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)


# --- stub external services so modules import without Docker -------------------
class _FakeRedis:
    def __init__(self): self.d = {}
    def get(self, k): return self.d.get(k)
    def set(self, k, v, ex=None, nx=False):
        if nx and k in self.d: return False
        self.d[k] = v if isinstance(v, bytes) else str(v).encode(); return True


for name in ("yfinance",):
    sys.modules.setdefault(name, types.ModuleType(name))
_rm = types.ModuleType("services.redis_manager"); _rm.get_redis_client = lambda: _FakeRedis()
_dm = types.ModuleType("services.db_manager"); _dm.get_engine = lambda: None; _dm.execute_query = lambda *a, **k: None
sys.modules["services.redis_manager"] = _rm
sys.modules["services.db_manager"] = _dm

from app.internal import finance as fx  # noqa: E402
from services.grounding import unsupported_numbers  # noqa: E402
import services.relationship_store as rs  # noqa: E402


class CapitalBudgeting(unittest.TestCase):
    CF = [-1000, 300, 400, 500, 200]

    def test_npv_matches_textbook(self):
        # Σ CF_t / 1.1^t, checked against numpy-financial: 115.5659
        self.assertAlmostEqual(fx.npv(0.10, self.CF), 115.5659, places=3)

    def test_irr_makes_npv_zero(self):
        r = fx.irr(self.CF)
        self.assertAlmostEqual(r, 0.153221, places=5)
        self.assertAlmostEqual(fx.npv(r, self.CF), 0.0, places=4)

    def test_irr_none_without_sign_change(self):
        self.assertIsNone(fx.irr([100, 100, 100]))

    def test_payback_interpolates(self):
        # cumulative: -1000, -700, -300, +200 → 2 + 300/500 = 2.6 years
        self.assertAlmostEqual(fx.payback_period(self.CF), 2.6)
        self.assertIsNone(fx.payback_period([-100, 10, 10]))

    def test_profitability_index(self):
        self.assertAlmostEqual(fx.profitability_index(0.10, self.CF), 1.115566, places=5)

    def test_wacc(self):
        # E=80, D=20, Re=10%, Rd=5%, t=25% → 0.8*0.10 + 0.2*0.05*0.75 = 8.75%
        self.assertAlmostEqual(fx.wacc(80, 20, 0.10, 0.05, 0.25), 0.0875)
        self.assertAlmostEqual(fx.capm_cost_of_equity(0.04, 1.2, 0.05), 0.10)


class Ratios(unittest.TestCase):
    def test_core_ratios(self):
        y = {"revenue": 100, "gross_profit": 60, "operating_income": 20, "net_income": 10, "equity": 50, "total_assets": 200,
             "total_debt": 40, "cash": 10, "current_assets": 30, "current_liabilities": 20, "inventory": 5,
             "interest_expense": -4, "ebitda": 30, "eps_diluted": 2.0, "dividends_paid": -6, "cost_of_revenue": 40}
        r = fx.compute_ratios(y, market_cap=500, price=40, dps_ttm=1.2)
        self.assertAlmostEqual(r["net_margin"], 0.10)
        self.assertAlmostEqual(r["roe"], 0.20)
        self.assertAlmostEqual(r["current_ratio"], 1.5)
        self.assertAlmostEqual(r["quick_ratio"], 1.25)
        self.assertAlmostEqual(r["interest_coverage"], 5.0)
        self.assertAlmostEqual(r["pe"], 20.0)
        self.assertAlmostEqual(r["ev_ebitda"], (500 + 40 - 10) / 30)
        self.assertAlmostEqual(r["dividend_yield"], 0.03)
        self.assertAlmostEqual(r["payout_ratio"], 0.6)

    def test_missing_data_gives_none_not_crash(self):
        r = fx.compute_ratios({"revenue": None}, None, None, None)
        self.assertIsNone(r["net_margin"])
        self.assertIsNone(r["pe"])


class NumberCheck(unittest.TestCase):
    CTX = "Net operating revenues were $47,061 million. Dividend yield 2.91%. P/E 28.45. Market cap $300.2B"

    def test_supported_with_rounding_and_units(self):
        self.assertEqual(unsupported_numbers("Revenue $47.1 billion, yield 2.91%, P/E 28.5, cap $300 billion", self.CTX), [])

    def test_flags_invented_numbers(self):
        self.assertEqual(unsupported_numbers("Margin 31.2% and yield 3.1%", self.CTX), ["3.1%", "31.2%"])

    def test_ignores_years_and_small_counts(self):
        self.assertEqual(unsupported_numbers("In 2024 it had 3 segments", self.CTX), [])


class RelationshipChecks(unittest.TestCase):
    SRC = ("The Company competes with PepsiCo, Inc. and Keurig Dr Pepper Inc. in the nonalcoholic beverage segment. "
           "Our bottling partners include Coca-Cola Europacific Partners plc.")

    def test_quote_must_be_in_source_and_name_partner(self):
        self.assertTrue(rs.grounded("competes with PepsiCo, Inc. and Keurig Dr Pepper Inc.", self.SRC, ("PepsiCo", "PEP")))
        self.assertFalse(rs.grounded("PepsiCo is our biggest rival in all markets", self.SRC, ("PepsiCo", "PEP")))
        self.assertFalse(rs.grounded("competes with PepsiCo, Inc. and Keurig Dr Pepper Inc.", self.SRC, ("Monster", "MNST")))

    def test_relationship_types(self):
        self.assertEqual([rs.normalize_rel(x) for x in ["supplier", "Bottler", "PARTNER", None, "rival"]],
                         ["SUPPLIER", "CUSTOMER", None, None, "COMPETITOR"])

    def test_name_resolution(self):
        rs._NAME_INDEX.update(ts=9e18, idx={rs._norm_name("PepsiCo, Inc."): "PEP", rs._norm_name("Keurig Dr Pepper Inc."): "KDP"})
        rs._known_tickers = lambda: {"PEP": 1, "KDP": 1}
        self.assertEqual(rs.resolve("PepsiCo"), "PEP")
        self.assertEqual(rs.resolve("Keurig Dr Pepper"), "KDP")
        self.assertIsNone(rs.resolve("OpenAI"))
        self.assertIsNone(rs.resolve("various suppliers"))


class OutputPolicy(unittest.TestCase):
    """Recommendation language is removed from AI-written text; plain facts and quoted filings are kept.
    (The only rating Oracle shows comes from the fixed formula in app/internal/valuation.py, never from the AI.)"""

    def test_flags_advice(self):
        from services.policy import find
        for t in ["Investors should consider buying KO on dips.", "The stock looks undervalued.", "I would recommend a HOLD.",
                  "Our price target is $70.", "Shares are expected to rise after earnings.", "Verdict: BUY", "Momentum is bullish.",
                  "Shares will likely rise."]:
            self.assertTrue(find(t), t)

    def test_keeps_facts(self):
        from services.policy import find
        for t in ["Coca-Cola reported net operating revenues of $45.8B [S1].", "The company repurchased shares in a buyback.",
                  "Selling, general and administrative expenses were $13.1B.", 'The 10-K states "we expect demand to rise".',
                  "Apple accounted for 22% of net revenue."]:
            self.assertFalse(find(t), t)

    def test_enforce_drops_only_bad_sentence(self):
        from services.policy import enforce
        clean, removed = enforce("Revenue was $45.8B [S1]. Investors should buy the stock. Net margin was 23%.")
        self.assertIn("Revenue was $45.8B", clean)
        self.assertIn("Net margin was 23%", clean)
        self.assertNotIn("should buy", clean)
        self.assertEqual(len(removed), 1)


class AccountingChecks(unittest.TestCase):
    def _y(self, **kw):
        return {k: {"value": v} for k, v in kw.items()}

    def test_balance_sheet_and_gross_profit(self):
        from app.internal.statements import tie_outs
        ok = {c["check"]: c["passed"] for c in tie_outs(self._y(total_assets=100.0, liabilities_and_equity=100.0,
                                                                     revenue=50.0, cost_of_revenue=20.0, gross_profit=30.0))}
        self.assertTrue(all(ok.values()) and len(ok) >= 2)
        bad = tie_outs(self._y(total_assets=100.0, liabilities_and_equity=90.0, revenue=50.0, cost_of_revenue=20.0, gross_profit=35.0))
        self.assertEqual(sum(not c["passed"] for c in bad), 2)

    def test_missing_inputs_skip(self):
        from app.internal.statements import tie_outs
        self.assertEqual(tie_outs(self._y(revenue=10.0)), [])



class LinkMeaning(unittest.TestCase):
    """Revenue-share parsing must not credit a group total to one company."""

    def setUp(self):
        import re as _re
        src = open(os.path.join(os.path.dirname(__file__), "..", "app", "routers", "market.py")).read()
        self.ns = {"re": _re}
        exec(src[src.index("_SHORT = {"):src.index("def describe_link(")], self.ns)
        self.n = ["Apple", "Apple", "AAPL"]

    def test_single_group_each(self):
        so = self.ns["share_of"]
        self.assertEqual(so("Sales attributable to Apple, our largest end customer accounted for approximately 22% of our revenue", self.n), ("single", 22.0))
        self.assertEqual(so("our top three digital music accounts, Spotify, YouTube and Apple, accounted for approximately 41% of our total revenue", self.n)[0], "group")
        self.assertEqual(so("revenues from Samsung, Lenovo, Apple, and OPPO each comprised 10% or more of our consolidated revenues.", self.n), ("each", 10.0))

    def test_resale_is_not_a_customer(self):
        self.assertTrue(self.ns["is_resale"]("revenues from Apple products (iPhones, iPads) over 90.4%", self.n))
        self.assertFalse(self.ns["is_resale"]("Apple accounted for 15% of net revenue.", self.n))


class FactRouting(unittest.TestCase):
    def test_classify(self):
        from app.internal.fact_answers import classify
        self.assertEqual(classify("What was revenue last fiscal year?")["kind"], "metric")
        self.assertEqual(classify("Who are its key suppliers?")["kind"], "relationship")
        self.assertEqual(classify("Latest news")["kind"], "news")
        self.assertIsNone(classify("What risks does the 10-K highlight?"))
        self.assertIsNone(classify("Why did net income fall?"))
        c = classify("My friend sold SCHW on Sep 15 because it is volatile and keeps going down. Was it right?")
        self.assertEqual(c["kind"], "claim")
        self.assertTrue(c["since"].endswith("-09-15"))


class PlainLanguage(unittest.TestCase):
    """Plain-language templates: rounding, comparisons stated as facts, no judgement words, no advice."""
    T, S, X = "SCHW", "S&P 500 (SPY)", "Financial Services sector (XLF)"

    def pc(self, since=False):
        T, S, X = self.T, self.S, self.X
        d = {"ticker": T, "name": "Charles Schwab", "sector": "Financial Services", "as_of": "2026-11-06", "price": 79.42, "benchmarks": [S, X],
             "periods": [{"period": "1 month", T: -0.06, S: -0.02, X: -0.03}, {"period": "3 months", T: -0.150, S: -0.046, X: -0.06},
                         {"period": "Year to date", T: -0.090, S: 0.085, X: 0.05}, {"period": "1 year", T: -0.011, S: 0.097, X: 0.07},
                         {"period": "3 years", T: 0.726, S: 0.745, X: 0.55}],
             "up_months": 6, "down_months": 6, "high_52w": {"price": 98.65, "date": "2026-08-24"}, "low_52w": {"price": 76.1, "date": "2026-03-10"},
             "below_high": -0.195, "largest_fall_1y": -0.21, "volatility_1y": {T: 0.259, S: 0.136, X: 0.17}, "volatility_3m": {T: 0.31, S: 0.15, X: 0.19}}
        if since:
            d["since"] = {"date": "2026-09-15", "price_then": 90.1, "price_now": 79.42, "change": -0.1185, S: -0.031, X: -0.04}
        return d

    def test_rounding(self):
        from app.internal import explain as E
        self.assertEqual(E.money(47941000000), "$47.9 billion")
        self.assertEqual(E.money(132.4e9), "$132 billion")
        self.assertEqual(E.pct(0.2593), "26%")
        self.assertEqual(E.pct(-0.046, True), "−4.6%")
        self.assertEqual(E.pct(0.745), "75%")  # half-up, not banker's rounding

    def test_comparisons(self):
        from app.internal import explain as E
        self.assertEqual(E.as_much(0.259, 0.136), "about twice as much as")
        self.assertEqual(E.as_much(0.10, 0.104), "about as much as")
        self.assertEqual(E.level(0.30, 0.20), "higher than")
        self.assertIn("while the S&P 500 rose", E.change_vs(-0.09, 0.085))
        self.assertIn("about the same as", E.change_vs(0.726, 0.745))

    def test_term_explained_once(self):
        from app.internal.explain import Explainer
        ex = Explainer()
        self.assertIn("(", ex.t("volatility"))
        self.assertEqual(ex.t("volatility"), "volatility")

    def test_schw_lead_and_no_judgement_or_advice(self):
        from app.internal import explain as E
        from services.policy import find
        st = E.price_story(self.pc())
        lead = " ".join(st["lead"])
        self.assertIn("about twice as much as the overall market", lead)
        self.assertIn("below its August high", lead)
        cl = E.claim_story(self.pc(since=True))
        text = E.render(cl["lead"] + cl["since"], [("a", cl["swings"]), ("b", cl["direction"])], cl["means"])
        for word in (" good ", " bad ", " strong ", " weak ", " cheap ", " risky ", "undervalued", "overvalued"):
            self.assertNotIn(word, text.lower())
        for sentence in text.replace("\n", " ").split(". "):
            self.assertFalse(find(sentence), sentence)
        self.assertIn("What it doesn't tell you", text)


class ValuationAndRating(unittest.TestCase):
    """The rating engine must reproduce the team report on Coca-Cola from the report's own inputs
    (cost of equity 7.16%, DDM $101.90, P/E $89.63, analysts $97.75 -> fair value ~$96.43 -> HOLD at $95.67)."""

    def inputs(self, **over):
        g = 1.05
        i = {"ticker": "KO", "name": "Coca-Cola", "currency": "USD", "price": 95.67, "risk_free": 0.0486, "raw_beta": 0.27, "erp": 0.045,
             "d0": 2.20 / g, "dps_history": [(2021 + k, g ** k) for k in range(5)],
             "pe_history": [{"year": str(2021 + k), "price": 25.4 * e, "eps": e} for k, e in enumerate((2.25, 2.19, 2.47, 2.46, 3.04))],
             "eps": 3.53, "eps_basis": "2027 estimate", "eps_last": 3.04, "analyst_target": 97.75, "analyst_count": 25,
             "interest_coverage": 8.3, "debt_to_equity": 1.33}
        i.update(over)
        return i

    def test_reproduces_the_report(self):
        from app.internal.valuation import assess
        v = assess(self.inputs())
        self.assertAlmostEqual(v["cost_of_equity"]["beta"], 0.51, places=2)      # Blume: 0.67 x 0.27 + 0.33
        self.assertAlmostEqual(v["cost_of_equity"]["ke"], 0.0716, places=4)
        ddm, pe, an = v["methods"]
        self.assertAlmostEqual(ddm["value"], 101.90, delta=0.05)
        self.assertAlmostEqual(pe["value"], 89.63, delta=0.05)
        self.assertAlmostEqual(an["value"], 97.75)
        self.assertAlmostEqual(v["fair_value"], 96.43, delta=0.05)
        self.assertEqual(v["rating"], "HOLD")
        self.assertAlmostEqual(v["buy_below"], 86.8, delta=0.1)                  # report: accumulate below ~$86
        self.assertAlmostEqual(v["sell_above"], 106.1, delta=0.1)                # report: trim above ~$106

    def test_bands(self):
        from app.internal.valuation import assess, rate
        self.assertEqual(assess(self.inputs(price=85.0))["rating"], "BUY")
        self.assertEqual(assess(self.inputs(price=107.0))["rating"], "SELL")
        self.assertEqual(rate(100, 100)["rating"], "HOLD")
        self.assertIsNone(rate(None, 100)["rating"])

    def test_methods_that_do_not_apply_are_left_out(self):
        from app.internal.valuation import assess
        v = assess(self.inputs(d0=None, dps_history=[]))                          # no dividend: two methods, still rated
        self.assertFalse(v["methods"][0]["available"])
        self.assertEqual(v["methods_used"], 2)
        self.assertAlmostEqual(v["fair_value"], (89.662 + 97.75) / 2, delta=0.05)
        v = assess(self.inputs(d0=None, dps_history=[], analyst_target=None))     # one method only: no rating
        self.assertIsNone(v["rating"])
        self.assertIn("why_none", v)
        v = assess(self.inputs(currency="TWD"))                                   # foreign filer: per-share figures don't match the ADR
        self.assertIsNone(v["rating"])

    def test_no_rating_when_methods_disagree_too_much(self):
        from app.internal.valuation import assess
        v = assess(self.inputs(d0=None, dps_history=[], analyst_target=200.0))    # P/E says ~$90, analysts $200
        self.assertIsNone(v["rating"])
        self.assertEqual(v["indicative"], "BUY")
        self.assertIn("disagree", v["why_none"])
        self.assertTrue(assess(self.inputs(price=86.0))["near_line"])            # within 2% of the BUY line

    def test_dividend_method_needs_a_real_payout(self):
        from app.internal.valuation import assess
        v = assess(self.inputs(payout=0.13))                                      # e.g. a company paying out 13% of profit
        self.assertFalse(v["methods"][0]["available"])
        self.assertEqual(v["methods_used"], 2)
        self.assertTrue(assess(self.inputs(payout=0.67))["methods"][0]["available"])

    def test_dividend_growth_is_capped_below_required_return(self):
        from app.internal.valuation import ddm, dividend_growth
        g = dividend_growth([(2020 + k, 1.12 ** k) for k in range(6)])           # 12% a year
        m = ddm(2.0, g, 0.08)
        self.assertTrue(m["g_capped"])
        self.assertAlmostEqual(m["g"], 0.06)
        self.assertAlmostEqual(m["value"], 2.0 * 1.06 / 0.02)

    def test_model_portfolio_matches_the_report(self):
        from app.internal.valuation import model_portfolio
        funds = {"VTI": {"beta": 1.02, "yield": 0.0103}, "VXUS": {"beta": 0.98, "yield": 0.026}, "BND": {"beta": 0.2, "yield": 0.0403},
                 "SGOV": {"beta": 0.0, "yield": 0.0385}, "VNQ": {"beta": 0.53, "yield": 0.0348}}
        p = model_portfolio("KO", "Coca-Cola", 0.51, 0.0486, 0.045, 0.0222, funds)
        self.assertAlmostEqual(sum(r["weight"] for r in p["rows"]), 1.0)
        self.assertAlmostEqual(p["total"]["beta"], 0.56, places=2)
        self.assertAlmostEqual(p["total"]["expected_return"], 0.071, places=3)
        self.assertAlmostEqual(p["total"]["yield"], 0.0260, places=4)
        self.assertAlmostEqual(p["total"]["stress"], -0.158, places=3)
        self.assertAlmostEqual(p["position_sizing"]["portfolio_cost"], -0.0375)

    def test_story_states_rule_and_limits(self):
        from app.internal.valuation import assess
        from app.internal.explain import rating_story, rating_text
        v = assess(self.inputs())
        v["story"] = rating_story(v)
        text = rating_text(v)
        self.assertIn("**HOLD**", text)
        self.assertIn("under $86.7", text)
        self.assertIn("It isn't personal advice", text)

    def test_rating_questions_are_routed_to_the_formula(self):
        from app.internal.fact_answers import classify
        for q in ("Should I buy KO?", "Is it a buy, hold or sell?", "Is SCHW overvalued?", "What is the fair value?"):
            self.assertEqual(classify(q)["kind"], "rating", q)
        self.assertEqual(classify("How would I build a portfolio around it?")["kind"], "portfolio")


if __name__ == "__main__":
    unittest.main()
