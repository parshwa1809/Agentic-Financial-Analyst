"""
Answers that need no AI: questions about a reported figure, a ratio, the price or documented
relationships are answered straight from SEC data / stored evidence, with the filing as the source.

Why: these answers are exact (copied from the SEC XBRL data, not paraphrased by a model), instant,
and cost zero AI requests. Only questions that need reading or explaining text go to the LLM.
"""
import re
from typing import Dict, List, Optional

# question words -> statement items / ratios
METRICS = [
    (r"\brevenue|\bsales\b|top[- ]line|turnover", ["revenue"]),
    (r"net income|net profit|\bprofit\b|\bearnings\b(?! (date|call|report|release))", ["net_income"]),
    (r"operating income|operating profit|\bebit\b", ["operating_income"]),
    (r"gross profit", ["gross_profit"]),
    (r"\beps\b|earnings per share", ["eps_diluted"]),
    (r"free cash ?flow|\bfcf\b", ["free_cash_flow"]),
    (r"operating cash ?flow|cash from operations", ["operating_cash_flow"]),
    (r"\bcapex\b|capital expenditure|capital spending", ["capex"]),
    (r"\bdebt\b|leverage|borrowing", ["total_debt", "debt_to_equity"]),
    (r"\bcash\b(?! ?flow)", ["cash"]),
    (r"shareholders'? equity|stockholders'? equity|book value", ["equity"]),
    (r"total assets", ["total_assets"]),
    (r"dividend", ["dps", "dividend_yield", "payout_ratio"]),
    (r"gross margin", ["gross_margin"]),
    (r"operating margin", ["operating_margin"]),
    (r"net margin|profit margin|\bmargins?\b", ["net_margin", "operating_margin", "gross_margin"]),
    (r"\broe\b|return on equity", ["roe"]),
    (r"\broa\b|return on assets", ["roa"]),
    (r"current ratio|liquidity", ["current_ratio", "quick_ratio"]),
    (r"interest coverage", ["interest_coverage"]),
    (r"p/?e\b|price[- ]to[- ]earnings|earnings multiple", ["pe"]),
    (r"p/?b\b|price[- ]to[- ]book", ["pb"]),
    (r"shares outstanding|share count|diluted shares", ["diluted_shares"]),
]
PRICE_RX = re.compile(r"\b(stock price|share price|price of|trading at|current price|what.{0,10}price|quote)\b", re.I)
REL_RX = {
    "SUPPLIER": re.compile(r"\bsuppl(y|ier|iers)\b|\bvendors?\b|who (makes|manufactures) ", re.I),
    "CUSTOMER": re.compile(r"\bcustomers?\b|\bclients?\b|who buys", re.I),
    "COMPETITOR": re.compile(r"\bcompet(e|es|itor|itors|ition)\b|\brivals?\b|\bpeers?\b", re.I),
}
# questions that need reading or explaining text -> AI path
NEEDS_TEXT = re.compile(r"\b(why|explain|how did|how does|what drove|driver|reason|risk|strategy|outlook|guidance|"
                        r"lawsuit|management|segment|plan|think|opinion|should|compare .* (with|to))\b", re.I)
NEWS_RX = re.compile(r"\b(news|headlines?|latest|recent|this week|today)\b", re.I)
HISTORY_RX = re.compile(r"\b(trend|over time|history|historical|growth|grow|grew|past (\d+ )?years|over the years|each year|by year|last \d+ years|years)\b", re.I)

ITEM_LABEL = {"revenue": "Revenue", "net_income": "Net income", "operating_income": "Operating income", "gross_profit": "Gross profit",
              "eps_diluted": "Diluted EPS", "free_cash_flow": "Free cash flow", "operating_cash_flow": "Operating cash flow",
              "capex": "Capital expenditure", "total_debt": "Total debt", "cash": "Cash & equivalents", "equity": "Shareholders' equity",
              "total_assets": "Total assets", "dps": "Dividends per share", "diluted_shares": "Diluted shares"}


def _money(v, cur):
    if v is None:
        return "not reported"
    a = abs(v)
    s = f"{a / 1e9:,.2f} billion" if a >= 1e9 else f"{a / 1e6:,.1f} million"
    return f"{'-' if v < 0 else ''}{'$' if cur == 'USD' else ''}{s}{'' if cur == 'USD' else ' ' + cur}"


def _fmt_item(k, v, cur):
    if v is None:
        return "not reported"
    if k in ("eps_diluted", "dps"):
        return f"{'$' if cur == 'USD' else ''}{v:.2f}{'' if cur == 'USD' else ' ' + cur}"
    if k == "diluted_shares":
        return f"{v / 1e9:.3f} billion shares"
    return _money(v, cur)


def _fmt_ratio(v, unit):
    if v is None:
        return "not available"
    return f"{v * 100:.1f}%" if unit == "%" else f"{v:.2f}x"


# "Buy, hold or sell?" / "is it overvalued?" -> the rule-based rating (app/internal/valuation.py), never the AI
RATING_RX = re.compile(r"\b(buy,? (hold|or sell)|hold or sell|should i (buy|sell|hold|invest)|is (it|this|[A-Za-z]{1,5}) (a|an) (buy|sell|hold|good investment)|"
                       r"worth (buying|investing)|good (investment|buy)|fair value|what is it worth|over-?valued|under-?valued|over-?priced|"
                       r"cheap|expensive|rating|recommendation|recommend|valuation|price target|cost of equity|required return)\b", re.I)
PORTFOLIO_RX = re.compile(r"\b(portfolio|diversif\w*|allocation|allocate|position siz\w*|how much (of|should|to (put|invest)))\b", re.I)
CLAIM_RX = re.compile(r"\b(volatil\w*|going down|keeps? (falling|dropping)|falling|dropp\w+|declin\w+|crash\w*|tank\w*|"
                      r"sold|sell|selling|bought|buy|right decision|mistake|was it (right|wrong|smart)|good decision)\b", re.I)
MONTHS = {m: i for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}


def _date_in(q: str):
    m = re.search(r"\b(20\d\d-\d\d-\d\d)\b", q)
    if m:
        return m.group(1)
    m = re.search(r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+(\d{1,2})(?:,?\s+(20\d\d))?", q, re.I)
    if m:
        from datetime import date
        y = int(m.group(3) or date.today().year)
        return f"{y}-{MONTHS[m.group(1).lower()[:3]]:02d}-{int(m.group(2)):02d}"
    return None


def classify(question: str):
    """-> {"kind": "metric"|"price"|"relationship"|"news"|"claim"|"rating"|"portfolio", ...} or None when the question needs the AI."""
    q = question.strip()
    if RATING_RX.search(q):
        return {"kind": "rating"}
    if PORTFOLIO_RX.search(q):
        return {"kind": "portfolio"}
    if CLAIM_RX.search(q):
        return {"kind": "claim", "since": _date_in(q)}
    if NEEDS_TEXT.search(q):
        return None
    if NEWS_RX.search(q) and not re.search(r"\b(revenue|income|eps|dividend|filing|10-?k)\b", q, re.I):
        return {"kind": "news"}
    rels = [r for r, rx in REL_RX.items() if rx.search(q)]
    if rels:
        return {"kind": "relationship", "types": rels}
    keys = []
    for rx, ks in METRICS:
        if re.search(rx, q, re.I):
            keys += [k for k in ks if k not in keys]
    if keys:
        years = re.findall(r"\b(20\d\d)\b", q)
        return {"kind": "metric", "keys": keys[:4], "years": years, "history": bool(HISTORY_RX.search(q))}
    if PRICE_RX.search(q):
        return {"kind": "price"}
    return None


def answer(question: str, ticker: str) -> Optional[Dict]:
    """Deterministic answer or None. Same response shape as the AI chat, with mode='facts'."""
    if not ticker:
        return None
    intent = classify(question)
    if not intent:
        return None
    if intent["kind"] == "relationship":
        return _relationships(ticker, intent["types"])
    if intent["kind"] == "news":
        return _news(ticker)
    if intent["kind"] == "claim":
        return _claim(ticker, intent.get("since"))
    if intent["kind"] == "rating":
        return _rating(ticker)
    if intent["kind"] == "portfolio":
        return _portfolio(ticker)
    from app.routers.research import market_price, _ratios
    from app.internal.finance import RATIO_DEFS
    mp = market_price(ticker)
    if intent["kind"] == "price":
        if not mp.get("price"):
            return None
        txt = f"{ticker} last traded at **${mp['price']:.2f}** ({mp['as_of']}, from {mp['source']}) [F1]."
        try:
            from app.internal.price_facts import price_check
            from app.internal.explain import price_story
            pcd = price_check(ticker)
            if "error" not in pcd:
                txt += " " + " ".join(price_story(pcd)["lead"]) + "\n\n" + price_story(pcd)["means"]
        except Exception:
            pass
        return _resp(txt, [_src("F1", f"{mp['source']} price", None, f"{ticker} {mp['price']:.2f} at {mp['as_of']}")])
    from app.internal.statements import verified_statements
    st = verified_statements(ticker)
    if not st["years"]:
        return None
    cur = st["currency"]
    years = st["years"]
    if intent["years"]:
        years = [y for y in years if y["fiscal_year_end"][:4] in intent["years"]] or years[:1]
    elif not intent["history"]:
        years = years[:1]
    from app.internal import explain as X
    from app.internal.research_data import get_profile
    try:
        name = get_profile(ticker).get("name") or ticker
    except Exception:
        name = ticker
    ex = X.Explainer()
    rdef = {d[0]: d for d in RATIO_DEFS}
    keys = intent["keys"]
    lines, sources, fid = [], [], {}

    def val(k, v):
        if k in ("eps_diluted", "dps"):
            return X.price(v, cur)
        if k == "diluted_shares":
            return f"{v / 1e9:.2f} billion shares"
        return X.money(v, cur)

    def fact_id(y, k):
        p = y["provenance"].get(k) or {}
        key = (p.get("url"), p.get("source"))
        if key not in fid:
            fid[key] = f"F{len(fid) + 1}"
            title = (f"{ticker} {p.get('form', '')} filed {p.get('filed', '')} (SEC XBRL)" if p.get("source", "").startswith("sec")
                     else f"{ticker} via Yahoo Finance (not verified)")
            sources.append(_src(fid[key], title, p.get("url"), p.get("concept") or p.get("formula") or p.get("note") or ""))
        return fid[key], p

    # --- lead: one or two plain sentences that answer the question --------------------------------
    lead = []
    new = years[0]
    is_latest = new is st["years"][0]
    prev = st["years"][1] if is_latest and len(st["years"]) > 1 else None
    item_keys = [k for k in keys if k in ITEM_LABEL]
    if len(years) >= 2:
        old = years[-1]
        n = int(new["fiscal_year_end"][:4]) - int(old["fiscal_year_end"][:4])
        for k in item_keys[:2]:
            a, b = new["items"].get(k), old["items"].get(k)
            if a is not None and b is not None and n > 0:
                per_year = f", about {X.pct((a / b) ** (1 / n) - 1)} a year" if a > 0 and b > 0 else ""
                who = f"{name}'s" if not lead else "Its"
                lead.append(f"{who} {ex.t(_GK.get(k, k), ITEM_LABEL[k].lower()) if _GK.get(k) else ITEM_LABEL[k].lower()} went from "
                            f"{val(k, b)} in fiscal {old['fiscal_year_end'][:4]} to {val(k, a)} in fiscal {new['fiscal_year_end'][:4]}{per_year}"
                            f" [{fact_id(new, k)[0]}].")
    else:
        for k in item_keys[:2]:
            v = new["items"].get(k)
            if v is None:
                continue
            ch = X._yoy(v, prev["items"].get(k)) if prev else None
            word = ex.t(_GK[k], ITEM_LABEL[k].lower()) if _GK.get(k) else ITEM_LABEL[k].lower()
            start = f"In the year ended {X.day(new['fiscal_year_end'])}, {name}'s" if not lead else "Its"
            lead.append(f"{start} {word} was **{val(k, v)}**"
                        f"{X._upby(ch)} [{fact_id(new, k)[0]}].")
    price_now = mp.get("price") if is_latest else None
    for k in [k for k in keys if k in rdef][:3]:
        if k in ("pe", "pb", "dividend_yield") and price_now is None:
            continue
        d = rdef[k]
        sent = X.ratio_sentence(k, d[1], _ratios(new["items"], price_now).get(k), d[4], ex)
        if sent:
            if prev and k not in ("pe", "pb", "dividend_yield", "ev_ebitda"):
                pv = _ratios(prev["items"], None).get(k)
                if pv is not None:
                    sent += f" The year before it was {X.pct(pv) if d[4] == '%' else X.times(pv) + ' times'}."
            lead.append(sent)

    # --- the numbers, year by year ---------------------------------------------------------------
    for y in years:
        price = mp.get("price") if y is st["years"][0] else None
        ratios = _ratios(y["items"], price)
        parts = []
        for k in keys:
            if k in ITEM_LABEL:
                v = y["items"].get(k)
                if v is None:
                    parts.append(f"{ITEM_LABEL[k]}: not reported")
                    continue
                f_, p = fact_id(y, k)
                tag = " ⚠ failed an accounting check" if p.get("check_failed") else ""
                calc = f" (calculated: {p['formula']})" if p.get("source") == "sec_calc" else ""
                parts.append(f"{ITEM_LABEL[k]} {val(k, v)}{calc}{tag} [{f_}]")
            elif k in rdef:
                if k in ("pe", "pb", "dividend_yield") and price is None:
                    continue
                d = rdef[k]
                v = ratios.get(k)
                parts.append(f"{d[1]} {'not available' if v is None else (X.pct(v) if d[4] == '%' else X.times(v) + ' times')} ({d[3]})")
        if parts:
            lines.append(f"Year ended {X.day(y['fiscal_year_end'])}: " + "; ".join(parts) + ".")
    if not lines:
        return None
    if any(k in ("pe", "pb", "dividend_yield") for k in keys) and mp.get("price"):
        fidp = f"F{len(sources) + 1}"
        sources.append(_src(fidp, f"{mp['source']} price", None, f"{mp['price']:.2f} at {mp['as_of']}"))
        lines.append(f"Share price used for price-based ratios: ${mp['price']:.2f} ({mp['as_of']}) [{fidp}].")
    if not lead:
        lead = [f"Here is what {name} reported to the {ex.t('sec')} in its {ex.t('10k', 'annual reports')}."]
    only_ratios = not item_keys
    text = X.render(lead, [(f"The numbers ({'US dollars' if cur == 'USD' else cur}, from the annual reports)", lines)],
                    X.means("ratio" if only_ratios else ("history" if len(years) > 1 else "financials")))
    return _resp(text, sources)


_GK = {"revenue": "revenue", "net_income": "net_income", "operating_income": "operating_income", "gross_profit": "gross_profit",
       "eps_diluted": "eps", "free_cash_flow": "free_cash_flow", "operating_cash_flow": "operating_cash_flow", "capex": "capex",
       "total_debt": "total_debt", "cash": "cash", "equity": "equity", "total_assets": "total_assets", "dps": "dividend",
       "diluted_shares": "shares_out"}


def _relationships(ticker: str, types: List[str]) -> Optional[Dict]:
    from app.routers.market import get_supply_chain
    ch = get_supply_chain(ticker, 1, False)
    links = [l for l in ch.get("links", []) if l.get("type") in types or ("SUPPLIER" in types and l.get("depends_on") == "partner_on_target")]
    label = {"SUPPLIER": "suppliers", "CUSTOMER": "customers", "COMPETITOR": "competitors"}
    if not links:
        return _resp(f"No {' or '.join(label[t] for t in types)} of {ticker} are documented with evidence yet. "
                     f"Oracle only lists a company when a filing or article names it; use Deep Dive → Research now to look again.", [])
    links.sort(key=lambda l: (-(l.get("share") or 0), l.get("source_type") != "filing"))
    lines, sources = [], []
    if "SUPPLIER" in types and not any(l.get("type") == "SUPPLIER" and l.get("depends_on") != "partner_on_target" for l in links):
        lines.append(f"- {ticker}'s own filings don't name its suppliers. The companies below name {ticker} as a major customer in their annual reports:")
    for i, l in enumerate(links[:8]):
        fid = f"F{i + 1}"
        sources.append(_src(fid, f"{l.get('disclosed_by') or ''} {('SEC filing' if l.get('source_type') == 'filing' else l.get('source_type'))}".strip(),
                            l.get("source_url"), l.get("evidence") or ""))
        lines.append(f"- **{l['target']}**: {l.get('statement') or l['type'].lower()} [{fid}]")
    from app.internal import explain as X
    ex = X.Explainer()
    kinds = " and ".join(ex.t(t.lower(), t.lower() + "s") for t in types)
    more = f"\n({len(links) - 8} more in Deep Dive.)" if len(links) > 8 else ""
    lead = (f"Oracle found {len(links)} {'company' if len(links) == 1 else 'companies'} documented as {ticker}'s {kinds} "
            f"in filings or news. Each one below comes with the sentence that names it; open a source to read it.")
    return _resp(lead + "\n\n" + "\n".join(lines) + more + "\n\n" + X.means("relationships"), sources)


def _news(ticker: str) -> Optional[Dict]:
    """Latest stored headlines with publisher and time. A list of what was published, not an interpretation."""
    from sqlalchemy import text
    from services.db_manager import get_engine
    with get_engine().connect() as conn:
        rows = conn.execute(text("SELECT headline, url, published_at FROM news_articles WHERE ticker=:t "
                                 "AND published_at >= NOW() - INTERVAL 7 DAY ORDER BY published_at DESC LIMIT 12"), {"t": ticker}).fetchall()
    seen, items = set(), []
    for h, u, p in rows:
        k = re.sub(r"\W+", " ", str(h).lower())[:60]
        if k in seen:
            continue
        seen.add(k)
        items.append((h, u, p))
        if len(items) == 6:
            break
    if not items:
        return _resp(f"No headlines about {ticker} were collected in the last 7 days.", [])
    lines, sources = [], []
    for i, (h, u, p) in enumerate(items):
        fid = f"N{i + 1}"
        pub = re.sub(r"^https?://(www\.)?([^/]+).*", r"\2", str(u or "")) or "publisher"
        sources.append({"id": fid, "title": str(h)[:120], "doc_type": "news", "url": u, "published_at": str(p), "score": 1.0,
                        "cited": True, "snippet": f"{pub} · {str(p)[:16]}"})
        lines.append(f"- {str(p)[:16]} · {h} [{fid}]")
    from app.internal.explain import means
    return _resp(f"Here are the {len(items)} most recent headlines about **{ticker}** from the last 7 days, newest first. "
                 f"Open a source to read the article.\n\n" + "\n".join(lines) + "\n\n" + means("news"), sources)


def _claim(ticker: str, since: Optional[str]) -> Optional[Dict]:
    """Test common buy/sell reasons against price data, in plain words. States what happened; never whether a decision was right."""
    from app.internal.price_facts import price_check
    from app.internal.explain import render
    d = price_check(ticker, since)
    if "error" in d:
        return None
    t, st = d["ticker"], d["story"]
    lead = [x for x in st["lead"]] + st["since"]
    if lead:
        lead[-1] = lead[-1] + " [P1]"
    sections = [("Is it volatile?", st["swings"]), ("Is it going down?", st["direction"])]
    text = render(lead, sections, st["means"])
    if not since:
        text += f"\n\nTip: add the date of the sale (e.g. \"sold {t} on 2026-09-15\") to see what the price did after it."
    text += f"\n\nPrices to {d['as_of']}, compared with the S&P 500 and the sector fund."
    src = _src("P1", "Yahoo Finance daily closes (adjusted) vs SPY and sector ETF (not verified)", f"https://finance.yahoo.com/quote/{t}/history",
               d["source"])
    src["doc_type"] = "data"
    return _resp(text, [src])


def _rating(ticker: str) -> Optional[Dict]:
    """Rule-based BUY / HOLD / SELL with the fair-value working, in plain words. A formula result, not an AI opinion."""
    from app.internal.explain import rating_text
    from app.internal.valuation import build
    try:
        v = build(ticker)
    except Exception as e:
        print(f"⚠️ valuation failed for {ticker}: {e}")
        return None
    sources = []
    for n, s in enumerate(v["inputs"], 1):
        val = s["value"]
        shown = "n/a" if val is None else f"{val * 100:.2f}%" if s["unit"] == "%" else f"{val:.2f}" if s["unit"] == "x" else f"${val:,.2f}"
        src = _src(f"R{n}", f"{s['input']}: {shown}", s.get("url"), s["source"])
        src["doc_type"] = "data"
        sources.append(src)
    return _resp(rating_text(v) + "\n\nThe full working, with a what-if table, is on Company Report → Investment view.", sources)


def _portfolio(ticker: str) -> Optional[Dict]:
    from app.internal.explain import render
    from app.internal.valuation import build_portfolio
    try:
        p = build_portfolio(ticker)
    except Exception as e:
        print(f"⚠️ model portfolio failed for {ticker}: {e}")
        return None
    st = p["story"]
    rows = [f"{r['symbol']} ({r['asset_class']}): {r['weight'] * 100:.0f}% = ${r['amount']:,.0f}" for r in p["rows"]]
    src = _src("P1", "Fund prices and distributions (Yahoo Finance; not verified)", "https://finance.yahoo.com/", p["source"])
    src["doc_type"] = "data"
    return _resp(render(st["lead"], [("In numbers", st["points"]), ("The holdings", rows)], st["means"])
                 + "\n\nThe table with every holding is on Company Report → Investment view.", [src])


def _src(fid, title, url, snippet):
    return {"id": fid, "title": title, "doc_type": "filing" if url and "sec.gov" in url else "data", "url": url,
            "published_at": None, "score": 1.0, "cited": True, "snippet": str(snippet)[:280]}


def _resp(text, sources):
    return {"response": text, "sources": sources, "unsupported_numbers": [], "policy_removed": [], "indexing": False,
            "model": None, "mode": "facts"}
