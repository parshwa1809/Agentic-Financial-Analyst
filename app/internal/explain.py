"""
Plain-language text for everything Oracle shows, built from templates and the shared glossary — no AI calls.

Rules (from the product brief):
  * Lead with one or two plain sentences that answer the question, then the numbers.
  * Explain each term the first time it appears ("volatility (how much the price swings day to day)").
  * Put each number in context: compare it with the S&P 500, the sector, peers or the company's own past.
    Comparisons are facts ("about twice as much as", "lower than"). Never call a number good, bad,
    strong, weak, cheap or risky — that is a judgement.
  * End with "What this means / what it doesn't tell you".
  * Round sensibly: $47.9 billion, 26%, 4.6%.
"""
from datetime import date
from typing import Dict, List, Optional

from app.internal.glossary import GLOSSARY

SPY = "S&P 500 (SPY)"
MONTH = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]


class Explainer:
    """Adds a glossary definition the first time a term is used in one answer."""

    def __init__(self):
        self.seen = set()

    def t(self, key: str, word: Optional[str] = None) -> str:
        g = GLOSSARY[key]
        word = word or g["term"]
        if key in self.seen:
            return word
        self.seen.add(key)
        return f"{word} ({g['short']})"

    def mark(self, *keys):
        """Treat terms as already explained (e.g. when the lead sentence explained them in other words)."""
        self.seen.update(keys)


# --------------------------------------------------------------------------- rounding & formatting
def _half_up(x: float, d: int = 0) -> float:
    m = 10 ** d
    return (int(abs(x) * m + 0.5) / m) * (1 if x >= 0 else -1)


def pct(v: Optional[float], signed: bool = False) -> str:
    """Fraction -> '26%', '4.6%'. One decimal below 10%, whole numbers from 10% up."""
    if v is None:
        return "n/a"
    x = v * 100
    d = 1 if abs(x) < 9.95 else 0
    r = _half_up(x, d)
    s = f"{abs(r):.{d}f}".rstrip("0").rstrip(".") if d else f"{abs(r):.0f}"
    sign = ("+" if r > 0 else "−" if r < 0 else "") if signed else ("−" if r < 0 else "")
    return f"{sign}{s}%"


def money(v: Optional[float], cur: str = "USD") -> str:
    """47941000000 -> '$47.9 billion'; non-USD amounts keep their currency code."""
    if v is None:
        return "not reported"
    a = abs(v)
    for size, word in ((1e12, "trillion"), (1e9, "billion"), (1e6, "million")):
        if a >= size:
            n = a / size
            s = f"{_half_up(n, 0 if n >= 100 else 1):,.{0 if n >= 100 else 1}f}".replace(".0 ", " ")
            if s.endswith(".0"):
                s = s[:-2]
            body = f"{s} {word}"
            break
    else:
        body = f"{a:,.0f}"
    pre = "−" if v < 0 else ""
    return f"{pre}${body}" if cur == "USD" else f"{pre}{body} {cur}"


def price(v: Optional[float], cur: str = "USD") -> str:
    if v is None:
        return "n/a"
    return f"${v:,.2f}" if cur == "USD" else f"{v:,.2f} {cur}"


def times(v: Optional[float]) -> str:
    if v is None:
        return "n/a"
    return f"{_half_up(v, 1 if abs(v) < 10 else 0):g}"


def day(iso: Optional[str]) -> str:
    """'2026-08-24' -> 'Aug 24, 2026'."""
    if not iso:
        return ""
    y, m, d = int(iso[:4]), int(iso[5:7]), int(iso[8:10])
    return f"{MONTH[m - 1][:3]} {d}, {y}"


def month(iso: Optional[str]) -> str:
    return MONTH[int(iso[5:7]) - 1] if iso else ""


def cite(*ids: str) -> str:
    return "".join(f"[{i}]" for i in ids if i)


# --------------------------------------------------------------------------- comparisons (facts, not verdicts)
def as_much(a: Optional[float], b: Optional[float]) -> Optional[str]:
    """Size of a compared with b: 'about twice as much as', 'about as much as', 'about half as much as'."""
    if a is None or not b:
        return None
    r = a / b
    if 0.9 <= r <= 1.1:
        return "about as much as"
    if 1.1 < r < 1.35:
        return "somewhat more than"
    if 1.35 <= r < 1.75:
        return "about one and a half times as much as"
    if 1.75 <= r < 2.25:
        return "about twice as much as"
    if 2.25 <= r < 2.75:
        return "about two and a half times as much as"
    if r >= 2.75:
        return f"about {int(_half_up(r))} times as much as"
    if 0.75 <= r < 0.9:
        return "somewhat less than"
    if 0.6 <= r < 0.75:
        return "about two-thirds as much as"
    if 0.4 <= r < 0.6:
        return "about half as much as"
    if 0.28 <= r < 0.4:
        return "about a third as much as"
    return "less than a quarter as much as"


def level(a: Optional[float], b: Optional[float], tol: float = 0.1) -> Optional[str]:
    """'higher than' / 'lower than' / 'about the same as' (within ±10% of b)."""
    if a is None or b is None:
        return None
    if abs(a - b) <= tol * abs(b) or abs(a - b) < 1e-9:
        return "about the same as"
    return "higher than" if a > b else "lower than"


def _moved(a: float) -> str:
    if abs(a) < 0.005:
        return "was about flat"
    return f"rose {pct(a)}" if a > 0 else f"fell {pct(-a)}"


def change_vs(a: Optional[float], b: Optional[float], bench: str = "the S&P 500") -> str:
    """'fell 15%, more than the S&P 500 (down 4.6%)' — a factual comparison of two price changes."""
    if a is None:
        return "has no price data for this period"
    if b is None:
        return _moved(a)
    bw = f"up {pct(b)}" if b > 0.005 else f"down {pct(-b)}" if b < -0.005 else "about flat"
    sg = lambda x: 1 if x > 0.005 else -1 if x < -0.005 else 0  # noqa: E731
    if sg(a) and sg(b) and sg(a) != sg(b):
        return f"{_moved(a)} while {bench} {'rose' if b > 0 else 'fell'} {pct(abs(b))}"
    close = abs(a - b) <= max(0.02, 0.1 * abs(b))
    if close:
        return f"{_moved(a)}, about the same as {bench} ({bw})"
    if a > 0:
        return f"{_moved(a)}, {'more' if a > b else 'less'} than {bench} ({bw})"
    return f"{_moved(a)}, a bigger fall than {bench} ({bw})" if a < b else f"{_moved(a)}, a smaller fall than {bench} ({bw})"


# --------------------------------------------------------------------------- "what this means" lines
MEANS = {
    "price": ("These numbers describe how the price behaved in the past, compared with the overall market.",
              "They don't predict what the price will do next, and they don't say whether to buy, hold or sell."),
    "claim": ("The data can check whether a reason matches what the price actually did.",
              "Whether a decision was right depends on things the data can't see: the price paid, the goal and time horizon, "
              "taxes, and what the money went into instead."),
    "financials": ("These are the company's own reported results for its last full year, as filed with the SEC.",
                   "They describe the past year; they don't say whether the stock is worth buying or what next year will look like."),
    "history": ("These are the figures the company reported to the SEC for each year shown, with the change calculated from them.",
                "Past growth doesn't say what will happen next, or whether the stock is worth buying."),
    "ratio": ("A ratio puts two reported numbers side by side so companies of different sizes can be compared.",
              "A higher or lower ratio isn't good or bad by itself; it depends on the industry and the company's situation."),
    "relationships": ("Each link is a business connection a filing or article names, with the quote that proves it.",
                      "Links only appear when they are disclosed, so this list is not every supplier or customer."),
    "news": ("These are the publishers' own headlines, listed as published.", "Headlines can carry the writer's opinion; Oracle doesn't check them."),
    "text": ("This answer summarises what the cited filings and articles say.",
             "It doesn't predict the future and doesn't say whether to buy, hold or sell."),
    "rating": ("The rating is the output of a published formula: the same inputs always give the same answer, and every input is listed so you can check it.",
               "It isn't personal advice. It ignores your goals, taxes and what you already own, and small changes in the assumptions "
               "can move the fair value a lot, especially in the dividend method."),
    "portfolio": ("This shows how the report's template portfolio would look with this stock as its core holding, using the formulas listed.",
                  "The percentages are a classroom template for a moderate-risk investor, not a plan for you, and expected returns are formula outputs, not promises."),
    "briefing": ("This is a summary of reported results and past price moves, each linked to its source.",
                 "It doesn't predict the future and doesn't say whether to buy, hold or sell."),
}


def means(kind: str) -> str:
    m, n = MEANS[kind]
    return f"**What this means:** {m} **What it doesn't tell you:** {n}"


# --------------------------------------------------------------------------- price facts in plain words
def _per(pc: Dict) -> Dict:
    return {r["period"]: r for r in pc.get("periods", [])}


def _sector(pc: Dict):
    sec = next((b for b in pc.get("benchmarks", []) if b != SPY), None)
    if not (sec and pc.get("sector")):
        return sec, None
    return sec, f"{sec.split('(')[-1].rstrip(')')}, a fund of large US {pc['sector'].lower()} companies"


def price_lead(pc: Dict) -> List[str]:
    """One or two sentences that answer 'how has the price behaved?'."""
    t = pc["ticker"]
    per = _per(pc)
    out = []
    vt, vs = pc["volatility_1y"].get(t), pc["volatility_1y"].get(SPY)
    am = as_much(vt, vs)
    if am:
        out.append(f"Over the past year {t}'s price moved up and down {am} the overall market (S&P 500).")
    below = pc.get("below_high") or 0
    y3, s3 = per.get("3 years", {}).get(t), per.get("3 years", {}).get(SPY)
    pos = (f"It is {pct(-below)} below its {month(pc['high_52w']['date'])} high" if below <= -0.03
           else "It is close to its highest price of the past year")
    if y3 is not None and s3 is not None:
        lvl = "about as much as" if abs(y3 - s3) <= max(0.03, 0.1 * abs(s3)) else ("more than" if y3 > s3 else "less than")
        verb = "rose" if y3 > 0 else "fell"
        joiner = "but" if (below <= -0.03) == (y3 > 0) else "and"
        tail = f"over 3 years it {verb} {lvl} the market" if (y3 > 0) == (s3 > 0) else f"over 3 years it {_moved(y3)} while the market {_moved(s3)}"
        out.append(f"{pos}, {joiner} {tail} ({pct(y3, True)} vs {pct(s3, True)}).")
    else:
        out.append(pos + ".")
    return out


def price_swings(pc: Dict, ex: Explainer) -> List[str]:
    t = pc["ticker"]
    v, v3 = pc["volatility_1y"], pc["volatility_3m"]
    vt, vs = v.get(t), v.get(SPY)
    sec, sec_words = _sector(pc)
    out = []
    if vt is not None and vs is not None:
        line = (f"{ex.t('volatility', 'Volatility')} over the past year: "
                f"{t} {pct(vt)}, the S&P 500 {pct(vs)} — {times(vt / vs)} times the market's.")
        if sec and v.get(sec):
            line += f" For {sec_words}, it was {pct(v[sec])}, so {t} swung {as_much(vt, v[sec])} its industry."
        out.append(line)
    if v3.get(t) is not None and v3.get(SPY):
        out.append(f"Volatility in the last 3 months only: {t} {pct(v3[t])} vs the S&P 500 {pct(v3[SPY])} ({as_much(v3[t], v3[SPY])} the market).")
    out.append(f"In the past 12 months the price rose in {pc['up_months']} months and fell in {pc['down_months']}.")
    if pc.get("largest_fall_1y") is not None:
        out.append(f"The {ex.t('drawdown')} within the past year was {pct(-pc['largest_fall_1y'])}.")
    return out


def price_direction(pc: Dict, ex: Explainer) -> List[str]:
    t, per = pc["ticker"], _per(pc)
    labels = [("1 month", "Last month"), ("3 months", "Last 3 months"), ("Year to date", "This year so far"),
              ("1 year", "Last 12 months"), ("3 years", "Last 3 years")]
    out = [f"{lab}: {t} {change_vs(per[p].get(t), per[p].get(SPY))}." for p, lab in labels if p in per and per[p].get(t) is not None]
    hi, lo = pc["high_52w"], pc["low_52w"]
    out.append(f"Today's price, {price(pc['price'])}, is {pct(-(pc.get('below_high') or 0))} below the {ex.t('high_52w')} "
               f"of {price(hi['price'])} ({day(hi['date'])}). The lowest close in that time was {price(lo['price'])} ({day(lo['date'])}).")
    return out


def price_story(pc: Dict) -> Dict:
    """Plain-language version of /price-check: lead, two sections, means line."""
    ex = Explainer()
    ex.mark("sp500")
    return {"lead": price_lead(pc), "swings": price_swings(pc, ex), "direction": price_direction(pc, ex), "means": means("price"),
            "as_of": pc.get("as_of")}


def claim_story(pc: Dict) -> Dict:
    """'My friend sold because it's volatile and going down' — test each reason against the price data."""
    t, per = pc["ticker"], _per(pc)
    ex = Explainer()
    ex.mark("sp500")
    lead = []
    vt, vs = pc["volatility_1y"].get(t), pc["volatility_1y"].get(SPY)
    if vt and vs:
        r = vt / vs
        am = as_much(vt, vs)
        if r >= 1.25:
            lead.append(f"\"Volatile\" matches the data: over the past year {t}'s price moved up and down {am} the overall market (S&P 500).")
        elif r <= 0.8:
            lead.append(f"\"Volatile\" doesn't match the data: over the past year {t}'s price moved up and down {am} the overall market (S&P 500).")
        else:
            lead.append(f"On \"volatile\": over the past year {t}'s price moved up and down about as much as the overall market (S&P 500).")
    m3, y1, y3 = (per.get(k, {}).get(t) for k in ("3 months", "1 year", "3 years"))
    s3m, s1, s3 = (per.get(k, {}).get(SPY) for k in ("3 months", "1 year", "3 years"))
    if m3 is not None:
        if m3 < -0.005:
            lead.append(f"\"Going down\" matches the last few months: in the past 3 months it {change_vs(m3, s3m, 'the market')}.")
        else:
            lead.append(f"\"Going down\" doesn't match the last few months: in the past 3 months it {change_vs(m3, s3m, 'the market')}.")
    if y3 is not None and s3 is not None:
        though = ", though," if (m3 is not None and m3 < -0.005 and y3 > 0) else ""
        lead.append(f"Over 3 years{though} it {change_vs(y3, s3, 'the market')}.")
    since = []
    if pc.get("since"):
        sn = pc["since"]
        since.append(f"Since {day(sn['date'])}, the date in your question, {t} went from {price(sn['price_then'])} to {price(sn['price_now'])}: "
                     f"it {change_vs(sn['change'], sn.get(SPY))} over the same days.")
    return {"lead": lead, "since": since, "swings": price_swings(pc, ex), "direction": price_direction(pc, ex),
            "means": means("claim"), "as_of": pc.get("as_of")}


# --------------------------------------------------------------------------- financial statements in plain words
def _yoy(a, b):
    return (a / b - 1) if a is not None and b and b > 0 and a > 0 else None


def _upby(ch: Optional[float], what: str = "the year before") -> str:
    if ch is None:
        return ""
    if abs(ch) < 0.005:
        return f", about the same as {what}"
    return f", {'up' if ch > 0 else 'down'} {pct(abs(ch))} from {what}"


def financial_lead(name: str, fy: str, it: Dict, prev: Optional[Dict], cur: str, ex: Explainer) -> str:
    rev, ni = it.get("revenue"), it.get("net_income")
    p = prev or {}
    parts = []
    if rev is not None:
        parts.append(f"In the year ended {day(fy)}, {name}'s {ex.t('revenue')} was {money(rev, cur)}{_upby(_yoy(rev, p.get('revenue')))}.")
    if ni is not None:
        verb = "made" if ni >= 0 else "lost"
        parts.append(f"It {verb} {money(abs(ni), cur)} of {ex.t('net_income')}{_upby(_yoy(ni, p.get('net_income')))}.")
    return " ".join(parts)


def financial_points(it: Dict, ra: Dict, peers_med: Dict, peer_names: str, growth: Dict, cur: str, ex: Explainer,
                     pe_note: str = "") -> List[str]:
    """Plain sentences for margins, cash, debt, growth and P/E; each compared with peers where available."""
    out = []
    peer = f"the companies Oracle compares it with ({peer_names})" if peer_names and peer_names != "none chosen" else None

    def vs_peer(k, fmt):
        if not peer or peers_med.get(k) is None or ra.get(k) is None:
            return ""
        return f" That is {level(ra[k], peers_med[k])} the {ex.t('median')} of {fmt(peers_med[k])} for {peer}."

    nm = ra.get("net_margin")
    if nm is not None:
        out.append(f"Out of every $100 of revenue, about ${int(_half_up(nm * 100))} was left as profit ({ex.t('net_margin')}: {pct(nm)})."
                   + vs_peer("net_margin", pct))
    roe = ra.get("roe")
    if roe is not None:
        out.append(f"Its {ex.t('roe')} was {pct(roe)}." + vs_peer("roe", pct))
    ocf, fcf = it.get("operating_cash_flow"), it.get("free_cash_flow")
    if ocf is not None:
        s = f"The business brought in {money(ocf, cur)} of {ex.t('operating_cash_flow')}"
        s += f"; after {ex.t('capex')}, {money(fcf, cur)} was left ({ex.t('free_cash_flow', 'free cash flow')})." if fcf is not None else "."
        out.append(s)
    de = ra.get("debt_to_equity")
    if de is not None and it.get("total_debt") is not None:
        out.append(f"It owed {money(it['total_debt'], cur)} of {ex.t('total_debt')}, {times(de)} times its {ex.t('equity')}."
                   + vs_peer("debt_to_equity", lambda x: f"{times(x)} times"))
    n = growth.get("years")
    if n and (growth.get("revenue") is not None or growth.get("net_income") is not None):
        g = [f"revenue about {pct(growth['revenue'])}" if growth.get("revenue") is not None else "",
             f"net income about {pct(growth['net_income'])}" if growth.get("net_income") is not None else ""]
        out.append(f"Over the last {n} years, {' and '.join(x for x in g if x)} a year on average ({ex.t('cagr')}).")
    pe = ra.get("pe")
    if pe is not None and pe > 0:
        out.append(f"Its {ex.t('pe')} is {times(pe)}, using the last fiscal year's profit{pe_note}." + vs_peer("pe", times))
    return out


def ratio_sentence(key: str, label: str, v: Optional[float], unit: str, ex: Explainer) -> Optional[str]:
    """One plain sentence for a single ratio (used by the no-AI chat answers)."""
    if v is None:
        return None
    gk = {"debt_to_equity": "debt_to_equity", "dividend_yield": "dividend_yield", "payout_ratio": "payout_ratio"}.get(key, key)
    term = ex.t(gk, label) if gk in GLOSSARY else label
    if key in ("net_margin", "operating_margin", "gross_margin", "fcf_margin"):
        left = {"net_margin": "left as profit after all costs", "operating_margin": "left as profit from the main business",
                "gross_margin": "left after the direct cost of what was sold", "fcf_margin": "left as free cash"}[key]
        return f"{term[0].upper() + term[1:]}: {pct(v)} — about ${int(_half_up(v * 100))} of every $100 of revenue was {left}."
    if key == "pe":
        return f"{term}: {times(v)} — the share price equals about {int(_half_up(v))} years of last year's profit per share."
    if key == "dividend_yield":
        return f"{term.capitalize()}: {pct(v)} — about ${_half_up(v * 100, 2):.2f} a year in dividends for every $100 of stock, at today's price."
    if key == "payout_ratio":
        return f"{term.capitalize()}: {pct(v)} of the year's profit was paid out as dividends."
    if unit == "%":
        return f"{term[0].upper() + term[1:]}: {pct(v)}."
    return f"{term[0].upper() + term[1:]}: {times(v)} times."


# --------------------------------------------------------------------------- valuation & rating in plain words
def r2(v: Optional[float]) -> str:
    """Rates in formulas keep two decimals: 7.16%."""
    return "n/a" if v is None else f"{v * 100:.2f}%"


def x1(v: Optional[float]) -> str:
    return "n/a" if v is None else f"{v:.1f}"


def _gap_words(price: float, fair: float) -> str:
    g = price / fair - 1
    if abs(g) < 0.005:
        return "about equal to"
    return f"{pct(abs(g))} {'above' if g > 0 else 'below'}"


def method_line(m: Dict, ex: Explainer) -> str:
    if not m["available"]:
        return f"{m['name']}: not used, because {m['why']}."
    if m["key"] == "ddm":
        cap = " (its past growth was higher; the model caps it 2 points below the required return)" if m["g_capped"] and m["g_history"] > m["g"] else ""
        gr = m["growth"]
        return (f"{ex.t('ddm', 'Dividend method')}: **{price(m['value'])}**. It assumes next year's dividend is {price(m['d1'])} a share and that "
                f"dividends keep growing {pct(m['g'])} a year, the company's own pace from {gr['from_year']} to {gr['to_year']}{cap}.")
    if m["key"] == "pe":
        return (f"{ex.t('hist_pe', 'Past price-tag method')}: **{price(m['value'])}**. At the last {m['years']} fiscal year-ends investors paid on average "
                f"{x1(m['avg_pe'])} times the year's profit per share (the P/E). Applied to expected profit of {price(m['eps'])} a share "
                f"({m['eps_basis']}).")
    n = f"{m['count']} analysts" if m.get("count") else "analysts"
    return f"{ex.t('analyst_target', 'Analysts’ average target')}: **{price(m['value'])}**, from {n} (Yahoo Finance; not verified)."


def risk_line(r: Dict, t: str) -> str:
    head = f"{r['risk']} — {r['level']}."
    if "cur_pe" in r:
        d = r["derate"]
        body = (f"Investors pay {x1(r['cur_pe'])} times last fiscal year's profit per share today; at recent year-ends the average was {x1(r['avg_pe'])}. "
                f"If that went back to the average with profit unchanged, the price would be {pct(abs(d))} {'lower' if d < 0 else 'higher'}.")
    elif "yield" in r:
        body = (f"The dividend yield is {pct(r['yield'])}; a 10-year US Treasury pays {pct(r['risk_free'])}. "
                + ("Income-focused investors can earn more from Treasuries, so the price is more exposed if rates rise." if r["yield"] < r["risk_free"]
                   else "The dividend pays at least as much as Treasuries."))
    elif "coverage" in r:
        de = f" Debt is {times(r['debt_to_equity'])} times shareholders' equity." if r.get("debt_to_equity") is not None else ""
        body = f"Operating profit covered the year's interest {times(r['coverage'])} times.{de}"
    elif "beta" in r:
        body = (f"Raw beta {r['beta']:.2f}: in months when the S&P 500 moved 1%, {t} typically moved about {abs(r['beta']):.1f}% "
                f"in the {'same' if r['beta'] >= 0 else 'opposite'} direction.")
    else:
        body = f"The methods range from {price(r['low'])} to {price(r['high'])}, a gap of {pct(r['spread'])} of fair value."
    return f"{head} {body} (Rule: {r['rule']}.)"


def rating_story(v: Dict) -> Dict:
    """Plain-language version of app/internal/valuation.py's result."""
    ex = Explainer()
    t, p, fair = v["ticker"], v["price"], v["fair_value"]
    coe = v["cost_of_equity"]
    lead = []
    if v.get("rating"):
        lead.append(f"Oracle's formula gives {t} a **{v['rating']}**. The share price, {price(p)}, is {_gap_words(p, fair)} the estimated "
                    f"{ex.t('fair_value')} of **{price(fair)}**.")
        lead.append(f"The rule: BUY when the price is more than {v['band'] * 100:.0f}% below fair value (under {price(v['buy_below'])}), "
                    f"SELL when it is more than {v['band'] * 100:.0f}% above (over {price(v['sell_above'])}), otherwise HOLD.")
        if v.get("near_line"):
            edge = v["buy_below"] if abs(p / v["buy_below"] - 1) < abs(p / v["sell_above"] - 1) else v["sell_above"]
            lead.append(f"This is close to the line: the price is within 2% of {price(edge)}, so a small move in the price or in one "
                        f"assumption would change the rating.")
    else:
        lead.append(f"Oracle's formula gives {t} **no rating**. {v.get('why_none', '')}")
        if v.get("indicative"):
            lead.append(f"The three estimates run from {price(v['low'])} to {price(v['high'])}. Their average is {price(fair)}; the price is {price(p)}. "
                        f"Under the ±{v['band'] * 100:.0f}% rule that would read {v['indicative']}, but Oracle doesn't show a rating built on estimates this far apart.")
    used = v["methods_used"]
    methods = [method_line(m, ex) for m in v["methods"]]
    if fair:
        methods.append(f"Fair value = the plain average of the {used} method{'s' if used != 1 else ''} above = **{price(fair)}**.")
    ret = [f"{ex.t('cost_of_equity', 'Required return')}: **{r2(coe['ke'])}** a year = {r2(coe['risk_free'])} "
           f"({ex.t('risk_free')}) + {coe['beta']:.2f} ({ex.t('adj_beta')}; raw beta {coe['raw_beta']:.2f}) × {r2(coe['erp'])} "
           f"({ex.t('erp')}).",
           "This rate only feeds the dividend method: the higher the return investors ask for, the less future dividends are worth today."]
    d = v["dividends"]
    div = []
    if d["pays"]:
        y = f", a {ex.t('dividend_yield')} of {pct(d['yield'])} at today's price; a 10-year US Treasury pays {pct(d['risk_free'])}" if d.get("yield") else ""
        div.append(f"{t} paid {price(d['d0'])} a share in dividends over the last 12 months{y}.")
        n, s = d["history_years"], d["raises_in_a_row"]
        g = d.get("growth")
        if n >= 2:
            first, last = d["history"][0]["year"], d["history"][-1]["year"]
            raised = (f"It raised the dividend every year from {first} to {last}" if s == n - 1 else
                      f"It raised the dividend in each of the last {s} years" if s > 0 else f"The dividend was not raised in {last}")
            div.append(raised + (f"; growth averaged {pct(g['rate'])} a year." if g else "."))
        yrs = [x for x in d["years"] if x.get("payout") is not None]
        if yrs:
            x = yrs[-1]
            div.append(f"In fiscal {x['year']} it paid out {pct(x['payout'])} of its profit per share as dividends "
                       f"({price(x['dps'])} of {price(x['eps'])}).")
            if x.get("fcf_cover") is not None:
                cmp_ = "more than" if x["fcf_cover"] > 1.05 else "less than" if x["fcf_cover"] < 0.95 else "about the same as"
                div.append(f"That year's {ex.t('free_cash_flow')}, {money(x['free_cash_flow'])}, was {cmp_} the "
                           f"{money(x['dividends_paid'])} paid in dividends.")
    else:
        div.append(f"{t} doesn't pay a dividend, so the dividend method isn't used.")
    risks = [risk_line(r, t) for r in v["risks"]]
    risks.append("Not covered here: company-specific risks such as lawsuits, regulation or changing customer habits. "
                 "Ask the AI analyst \"What risks does its annual report mention?\" to read them from the 10-K.")
    return {"lead": lead, "methods": methods, "required_return": ret, "dividends": div, "risks": risks, "means": means("rating")}


def rating_text(v: Dict) -> str:
    st = v["story"]
    return render(st["lead"], [("How the fair value is calculated", st["methods"]), ("The return investors ask for", st["required_return"]),
                               ("Dividends", st["dividends"]), ("Risk checks", st["risks"])], st["means"])


def portfolio_story(p: Dict) -> Dict:
    ex = Explainer()
    t, tot, b = p["ticker"], p["total"], p["budget"]
    w = p["rows"][0]["weight"]
    lead = [f"Following the report's template, a ${b:,.0f} portfolio puts {pct(w)} (${b * w:,.0f}) in {t} and spreads the rest over five low-cost "
            f"{ex.t('index_fund', 'index funds')}: {pct(p['mix']['stocks'])} in stocks in total, {pct(p['mix']['real_estate'])} in real estate and "
            f"{pct(p['mix']['bonds_cash'])} in bonds and {ex.t('tbill')}."]
    pts = []
    if tot.get("beta") is not None:
        pts.append(f"It would be expected to move about {pct(tot['beta'])} as much as the stock market (portfolio beta {tot['beta']:.2f}).")
    if tot.get("expected_return") is not None:
        pts.append(f"{ex.t('expected_return', 'Expected return')} by the formulas: about {pct(tot['expected_return'])} a year.")
    if tot.get("income") is not None:
        pts.append(f"Income from dividends and interest: about ${tot['income']:,.0f} a year ({pct(tot['yield'])}).")
    pts.append(f"Fund fees: about ${tot['fees']:,.0f} a year ({tot['expense_ratio'] * 100:.2f}% of the money invested).")
    if tot.get("stress") is not None:
        pts.append(f"Bear-market test: in a what-if where {p['stress_scenario']}, the portfolio would fall about {pct(abs(tot['stress']))}, "
                   f"vs 30% for a portfolio of stocks only.")
    ps = p["position_sizing"]
    pts.append(f"Because {t} is only {pct(ps['weight'])} of the total, a 25% fall in {t} alone would cost the whole portfolio {pct(abs(ps['portfolio_cost']))}.")
    pts.append(f"{ex.t('rebalance', 'Rebalance')} {p['rebalance']}.")
    return {"lead": lead, "points": pts, "means": means("portfolio")}


def render(lead: List[str], sections: List[tuple], means_line: str) -> str:
    """Lead paragraph, then titled bullet sections, then the means line. Markdown: **bold** and '- ' bullets only."""
    parts = [" ".join(lead)]
    for title, lines in sections:
        if lines:
            parts.append(f"**{title}**\n" + "\n".join(f"- {x}" for x in lines))
    parts.append(means_line)
    return "\n\n".join(p for p in parts if p)


def today() -> str:
    return date.today().isoformat()
