"""
SEC EDGAR access for evidence-backed relationships.

Pulls a company's latest annual report (10-K, or 20-F for foreign filers such as
TSM), keeps only the passages that talk about customers, suppliers and
competitors, and returns them with the filing URL so every relationship we
extract can cite the exact document it came from.

EDGAR is free and needs no key, but the SEC asks every client to identify
itself. Set SEC_USER_AGENT in .env to "Your Name your@email.com".
"""
import html
import json
import os
import re
import time

import requests

from services.redis_manager import get_redis_client

UA = os.getenv("SEC_USER_AGENT", "ProjectOracle research tool (set SEC_USER_AGENT in .env)")
HEADERS = {"User-Agent": UA, "Accept-Encoding": "gzip, deflate"}
_r = get_redis_client()
_TICKERS_CACHE = {"ts": 0, "data": None}

KEYWORDS = re.compile(
    r"\b(customers?|suppliers?|vendors?|compet\w*|bottl\w*|distribut\w*|contract manufactur\w*|"
    r"sole[- ]source|single[- ]source|outsourc\w*|licens\w*|partner\w*|largest|significant portion|"
    r"accounted for|concentration)\b", re.I)
NAME_HINT = re.compile(r"\b[A-Z][A-Za-z&.\-]+(?:\s+[A-Z][A-Za-z&.\-]+){0,3}\b")


def _get(url: str, timeout: int = 30):
    time.sleep(0.15)  # stay well under SEC's 10 requests/second limit
    res = requests.get(url, headers=HEADERS, timeout=timeout)
    res.raise_for_status()
    return res


def company_tickers() -> dict:
    """{TICKER: {"cik": int, "title": str}} for every SEC registrant (cached 7 days)."""
    if _TICKERS_CACHE["data"] and time.time() - _TICKERS_CACHE["ts"] < 86400:
        return _TICKERS_CACHE["data"]
    try:
        raw = _r.get("sec:company_tickers")
        if raw:
            data = json.loads(raw)
        else:
            js = _get("https://www.sec.gov/files/company_tickers.json").json()
            data = {v["ticker"].upper(): {"cik": int(v["cik_str"]), "title": v["title"]} for v in js.values()}
            _r.set("sec:company_tickers", json.dumps(data), ex=7 * 86400)
    except Exception as e:
        print(f"      ⚠️ SEC ticker list unavailable: {e}")
        data = {}
    _TICKERS_CACHE.update(ts=time.time(), data=data)
    return data


def latest_annual_report(ticker: str):
    """(url, form, filing_date) of the newest 10-K / 20-F / 40-F, or None."""
    info = company_tickers().get(ticker.upper())
    if not info:
        return None
    cik = info["cik"]
    try:
        sub = _get(f"https://data.sec.gov/submissions/CIK{cik:010d}.json").json()
    except Exception as e:
        print(f"      ⚠️ EDGAR submissions failed for {ticker}: {e}")
        return None
    recent = sub.get("filings", {}).get("recent", {})
    for form, acc, doc, date in zip(recent.get("form", []), recent.get("accessionNumber", []),
                                    recent.get("primaryDocument", []), recent.get("filingDate", [])):
        if form in ("10-K", "20-F", "40-F"):
            url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc.replace('-', '')}/{doc}"
            return url, form, date
    return None


def html_to_text(raw: str) -> str:
    raw = re.sub(r"(?is)<(script|style|ix:header)[^>]*>.*?</\1>", " ", raw)
    raw = re.sub(r"(?i)<br\s*/?>|</(p|div|tr|li|h\d)>", "\n", raw)
    raw = re.sub(r"<[^>]+>", " ", raw)
    txt = html.unescape(raw).replace("\xa0", " ")
    txt = re.sub(r"[ \t]+", " ", txt)
    return re.sub(r"\n\s*\n+", "\n\n", txt)


ORG = re.compile(r"\b[A-Z][\w&.\-]*(?:\s+[A-Z][\w&.\-]*){0,4},?\s+(?:Inc\.?|Incorporated|Corporation|Corp\.?|Company|Co\.|"
                 r"Ltd\.?|Limited|plc|PLC|N\.V\.|S\.A\.|AG|SE|LLC|Holdings|Group)\b")
SECTION = re.compile(r"\b(competition|competitors|customers|suppliers|raw materials|bottl\w+|distribut\w+|"
                     r"major customer|concentration of|sole source|single source|contract manufactur\w+)\b", re.I)


def relationship_passages(ticker: str, max_chars: int = None):
    """Relationship-relevant passages from the latest annual report, preferring paragraphs that
    NAME other companies (Inc., Corporation, plc …) in a customer/supplier/competitor context.
    Returns {"url", "form", "filed", "text", "full_text"} or None. Cached 7 days per filing."""
    if max_chars is None:  # hosted 70B models read much more context than a small local model
        max_chars = 20000 if os.getenv("LLM_PROVIDER", "ollama") != "ollama" else 6000
    found = latest_annual_report(ticker)
    if not found:
        return None
    url, form, filed = found
    key = f"sec:passages:v2:{max_chars}:{url}"
    try:
        cached = _r.get(key)
        if cached:
            return json.loads(cached)
    except Exception:
        pass
    try:
        text = html_to_text(_get(url, timeout=60).text)
    except Exception as e:
        print(f"      ⚠️ Could not download {form} for {ticker}: {e}")
        return None

    scored = []
    for para in (p.strip() for p in text.split("\n\n")):
        if not (60 <= len(para) <= 3000):
            continue
        orgs = len({o for o in ORG.findall(para) if not re.match(r"(The|Our|This|Such|Each|Any)\s+(Company|Corporation|Group)", o)})
        sect = len(SECTION.findall(para))
        kw = len(KEYWORDS.findall(para))
        if not (orgs or sect):
            continue
        score = orgs * 6 + sect * 3 + min(kw, 6) + (8 if orgs and sect else 0)
        scored.append((score, para))
    scored.sort(key=lambda x: -x[0])
    picked, total = [], 0
    for _, para in scored:
        if total + len(para) > max_chars:
            continue
        picked.append(para)
        total += len(para)
    out = {"url": url, "form": form, "filed": filed, "text": "\n\n".join(picked), "full_text": text}
    try:
        _r.set(key, json.dumps(out), ex=7 * 86400)
    except Exception:
        pass
    return out


# ---------------------------------------------------------------------------------------------
# Reverse disclosure search: suppliers must disclose big customers in their own 10-Ks
# ("Apple accounted for 22% of net revenue"). Searching other companies' filings for the
# target's name gives supplier links that are grounded by construction, with no LLM involved.
# ---------------------------------------------------------------------------------------------
CUST_CUE = re.compile(r"(accounted for|% of (?:our |its |total |net )*(?:net )?(?:revenue|sales)|largest customer|"
                      r"significant customer|major customer|customers? (?:include|such as)|sells? (?:to|its products to)|"
                      r"concentration)", re.I)


def _core_name(title: str) -> str:
    t = re.sub(r"[,.]?\s+(inc|incorporated|corp|corporation|co|company|ltd|limited|plc|holdings?|group|n\.v|s\.a)\.?$", "",
               title.strip(), flags=re.I)
    return re.sub(r"^the\s+", "", t, flags=re.I).strip()


def customer_disclosures(ticker: str, max_filings: int = 8):
    """[{supplier_ticker, quote, url, filed}] from other companies' annual reports that name `ticker`
    as a customer. Cached 7 days."""
    t = ticker.upper()
    key = f"sec:custdisc:v4:{t}"
    try:
        hit = _r.get(key)
        if hit:
            return json.loads(hit)
    except Exception:
        pass
    tickers = company_tickers()
    info = tickers.get(t)
    if not info:
        return []
    core = _core_name(info["title"])
    if len(core) < 3:
        return []
    # Filings often use a short or trading name instead of the legal one
    SHORT = {"TSM": "TSMC", "GOOGL": "Google", "GOOG": "Google", "META": "Meta", "BRK.B": "Berkshire", "JPM": "JPMorgan",
             "WMT": "Walmart", "AMZN": "Amazon", "NVDA": "NVIDIA", "TSLA": "Tesla", "MSFT": "Microsoft", "AAPL": "Apple"}
    core = SHORT.get(t, core)
    by_cik = {}
    for tk, v in tickers.items():
        if v["cik"] not in by_cik or len(tk) < len(by_cik[v["cik"]]):
            by_cik[v["cik"]] = tk
    try:
        res = _get(f'https://efts.sec.gov/LATEST/search-index?q=%22{requests.utils.quote(core)}%22%20%22accounted%20for%22&forms=10-K,20-F'
                   f'&dateRange=custom&startdt={time.strftime("%Y-%m-%d", time.gmtime(time.time() - 2 * 365 * 86400))}'
                   f'&enddt={time.strftime("%Y-%m-%d")}').json()
        hits = res.get("hits", {}).get("hits", [])
    except Exception as e:
        print(f"      ⚠️ EDGAR full-text search failed for {t}: {e}")
        return []
    out, seen = [], set()
    n = re.escape(core)  # case-sensitive: "Apple" the company, not "apple polyphenols"
    as_customer = [
        # "Apple accounted for 22% of net revenue", "Apple ... represented approximately 15% of sales"
        re.compile(r"\b" + n + r"\b(?:\W+\w+){0,12}?\W+(?:accounted for|accounting for|represented|representing|comprised)\W+(?:approximately\W+|about\W+|more than\W+|over\W+)?\d+(?:\.\d+)?\s?%[^.]{0,80}?(?:revenue|sales)"),
        # "sales to Apple", "revenue from Apple", "customers include Apple"
        re.compile(r"(?:sales to|revenues? from|customers? (?:include|including|such as)|our largest customers?(?:,| is| was| were)?)\W+(?:\w+\W+){0,8}?" + n + r"\b"),
    ]
    resale = re.compile(r"pre-owned|refurbished|used " + n + r"|resell|accounts receivable|" + n + r"\s+(?:products|devices|branded)", re.I)
    for h in hits:
        src = h.get("_source", {})
        ciks = [int(c) for c in src.get("ciks", []) if str(c).isdigit()]
        sup = next((by_cik[c] for c in ciks if c in by_cik), None)
        if not sup or sup == t or sup in seen:
            continue
        adsh, _, fname = h.get("_id", "").partition(":")
        if not adsh or not fname:
            continue
        url = f"https://www.sec.gov/Archives/edgar/data/{ciks[0]}/{adsh.replace('-', '')}/{fname}"
        try:
            body = html_to_text(_get(url, timeout=60).text)
        except Exception:
            continue
        for sent in re.split(r"(?<=[.;])\s+", body):
            if 40 < len(sent) < 600 and any(p.search(sent) for p in as_customer) and not resale.search(sent):
                out.append({"supplier": sup, "quote": re.sub(r"\s+", " ", sent).strip(), "url": url, "filed": src.get("file_date")})
                seen.add(sup)
                break
        if len(seen) >= max_filings:
            break
    try:
        _r.set(key, json.dumps(out), ex=7 * 86400)
    except Exception:
        pass
    return out
