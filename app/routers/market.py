import pandas as pd
import numpy as np
import math
import re
from fastapi import APIRouter, HTTPException
from datetime import datetime, timedelta
from sqlalchemy import text
from services.db_manager import get_engine
from services.indicators import calculate_rsi, calculate_bbands, calculate_vwap, calculate_macd, calculate_bandwidth

router = APIRouter()
engine = get_engine()

# --- HELPER: FORMAT NUMBERS ---
def format_number(num):
    if num is None: return "N/A"
    try:
        val = float(num)
        if math.isnan(val) or math.isinf(val): return "N/A"
    except: return "N/A"
    if val >= 1e12: return f"${val/1e12:.2f}T"
    if val >= 1e9: return f"${val/1e9:.2f}B"
    if val >= 1e6: return f"${val/1e6:.2f}M"
    return f"{val:.2f}"

# --- ENDPOINT: CANDLES ---
@router.get("/{ticker}/candles")
def get_candles(ticker: str, timeframe: str = "1D"):
    ticker = ticker.upper()
    mapping = {'1Min': 1, '5Min': 5, '15Min': 7, '1D': 1, '1W': 7, '1M': 30, '3M': 90, '1Y': 365}
    days = mapping.get(timeframe, 30)
    
    try:
        latest_query = text("SELECT MAX(timestamp) as last_ts FROM market_data WHERE ticker = :t")
        latest_df = pd.read_sql(latest_query, engine, params={"t": ticker})
        latest_ts = pd.to_datetime(latest_df.iloc[0]['last_ts']) if not latest_df.empty and latest_df.iloc[0]['last_ts'] else datetime.utcnow() 
        cutoff = latest_ts - timedelta(days=days)

        query = text("SELECT ticker, timestamp, open, high, low, close, volume FROM market_data WHERE ticker = :t AND timestamp >= :c ORDER BY timestamp ASC")
        df = pd.read_sql(query, engine, params={"t": ticker, "c": cutoff})
        
        if df.empty: return {"data": []}
        
        try:
            df['RSI'] = calculate_rsi(df['close'], 14)
            upper, middle, lower = calculate_bbands(df['close'])
            df['BandWidth'] = calculate_bandwidth(upper, lower, middle)
            df['VWAP'] = calculate_vwap(df)
            macd_line, _ = calculate_macd(df['close'])
            df['MACD'] = macd_line
        except Exception: pass

        df['timestamp'] = df['timestamp'].astype(str)
        df = df.astype(object)
        df.where(pd.notnull(df), None, inplace=True)
        return {"data": df.to_dict(orient="records")}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# --- ENDPOINT: STATS ---
@router.get("/{ticker}/stats")
def get_stats(ticker: str):
    ticker = ticker.upper()
    try:
        fund_query = text("SELECT * FROM fundamentals WHERE ticker=:t")
        fund = pd.read_sql(fund_query, engine, params={"t": ticker})
        stats = {"ratios": [], "source": "Yahoo Finance via yfinance (not verified; see Company Report for SEC figures)"}

        if not fund.empty:
            row = fund.iloc[0]
            mappings = [("market_cap", "Market Cap", "currency"), ("pe_ratio", "P/E Ratio", "number"), ("pb_ratio", "P/B Ratio", "number"), ("debt_to_equity", "Debt/Eq", "number"), ("profit_margin", "Margins", "percent"), ("dividend_yield", "Div Yield", "percent")]
            for col, label, fmt in mappings:
                val = row.get(col)
                display_val = "N/A"
                if val is not None and not pd.isna(val):
                    try:
                        f_val = float(val)
                        if fmt == "currency": display_val = format_number(f_val)
                        elif fmt == "percent":
                            # Newer yfinance returns dividendYield already in percent (0.41 = 0.41%),
                            # older versions as a fraction (0.0041). A yield above 20% is not plausible,
                            # so treat large values as percent-already instead of multiplying again.
                            if col == "dividend_yield" and f_val > 0.2: f_val = f_val / 100.0
                            display_val = f"{f_val*100:.2f}%"
                        else: display_val = f"{f_val:.2f}"
                    except: pass
                stats['ratios'].append({"label": label, "value": display_val, "key": col})
        return stats
    except Exception: return {"ratios": []}

# --- ENDPOINT: ALERTS ---
@router.get("/alerts")
def get_recent_alerts(ticker: str = None):
    try:
        query = text("SELECT ticker, message, created_at FROM active_alerts WHERE ticker=:t ORDER BY created_at DESC LIMIT 50") if ticker else text("SELECT ticker, message, created_at FROM active_alerts ORDER BY created_at DESC LIMIT 50")
        df = pd.read_sql(query, engine, params={"t": ticker.upper()} if ticker else {})
        if not df.empty:
            df['created_at'] = df['created_at'].astype(str)
            return df.to_dict(orient="records")
        return []
    except Exception: return []

# --- ENDPOINT: NEWS ---
@router.get("/news")
def get_market_news(ticker: str = None):
    try:
        query = text("SELECT ticker, headline, url, published_at, sentiment_score FROM news_articles WHERE ticker=:t ORDER BY published_at DESC LIMIT 20") if ticker else text("SELECT ticker, headline, url, published_at, sentiment_score FROM news_articles ORDER BY published_at DESC LIMIT 20")
        df = pd.read_sql(query, engine, params={"t": ticker.upper()} if ticker else {})
        if not df.empty:
            df['published_at'] = df['published_at'].astype(str)
            return df.to_dict(orient="records")
        return []
    except Exception: return []

# --- 3-WAY CATEGORY MAPPING ---
def normalize_relationship(rel_type):
    # Some agent-written rows have a NULL relationship; before this guard one bad row
    # crashed the whole endpoint and the map showed "No relationships" (e.g. AAPL).
    rel = str(rel_type or '').upper().strip()
    if rel in ['CUSTOMER', 'CLIENT', 'OEM', 'DISTRIBUTOR', 'RESELLER', 'BUYER']:
        return 'CUSTOMER'
    if rel in ['COMPETITOR', 'RIVAL', 'PEER', 'CHALLENGER']:
        return 'COMPETITOR'
    if rel in ['SUPPLIER', 'VENDOR', 'MANUFACTURER', 'PROVIDER', 'LICENSOR']:
        return 'SUPPLIER'
    return None  # ambiguous ("PARTNER") or missing: not shown as a supply-chain link

# --- SUPPLY CHAIN (deduplicated, with provenance) ---
_PROV_COLS = ["confidence", "source_type", "source_url", "evidence", "status", "first_seen", "last_verified", "n_sources"]


def _prov(row):
    out = {}
    for c in _PROV_COLS:
        v = row.get(c) if hasattr(row, "get") else None
        if v is None or (isinstance(v, float) and math.isnan(v)):
            out[c] = None
        elif c in ("first_seen", "last_verified"):
            out[c] = str(v)
        elif c in ("confidence",):
            out[c] = float(v)
        elif c == "n_sources":
            out[c] = int(v)
        else:
            out[c] = str(v)
    return out


# --- plain-English meaning of each link (deterministic, from the stored evidence) ---
_CIK_RX = re.compile(r"/edgar/data/(\d+)/")
_SHARE_RX = re.compile(r"(\d{1,2}(?:\.\d+)?)\s?%")


def _sec_maps():
    try:
        from services.sec_filings import company_tickers
        ct = company_tickers()
    except Exception:
        ct = {}
    by_cik = {}
    for tk, v in ct.items():
        if v["cik"] not in by_cik or len(tk) < len(by_cik[v["cik"]]):
            by_cik[v["cik"]] = tk
    names = {tk: v["title"] for tk, v in ct.items()}
    return by_cik, names


def _short(name: str, tk: str) -> str:
    n = re.sub(r"(?i)[,.]?\s+(inc|incorporated|corp|corporation|co|company|ltd|limited|plc|holdings?|group|n\.?v|s\.?a)\.?$", "", name or tk).strip()
    return n.title() if n.isupper() and len(n) > 4 else (n or tk)


_SHORT = {"TSM": ["TSMC"], "GOOGL": ["Google"], "GOOG": ["Google"], "META": ["Meta", "Facebook"], "AMZN": ["Amazon"],
          "MSFT": ["Microsoft"], "AAPL": ["Apple"], "NVDA": ["NVIDIA", "Nvidia"], "TSLA": ["Tesla"], "KO": ["Coca-Cola"]}
_VERB = r"(?:accounted for|accounting for|represented|representing|comprised|made up)"
_PCT = r"(?:approximately\W+|about\W+|more than\W+|over\W+|nearly\W+)?(\d{1,2}(?:\.\d+)?)\s?%"


def share_of(ev: str, names):
    """How much of the DISCLOSING company's revenue the named company is, as the sentence states it.
    -> ("single", 22.0) | ("each", 10.0) meaning >=10% | ("group", 80.6) combined with others | None."""
    names = [n for n in names if n and len(n) >= 3]
    if not names or not re.search(r"(?i)revenue|sales", ev):
        return None
    nrx = "(?:" + "|".join(re.escape(n) for n in names) + ")"
    if not re.search(r"\b" + nrx + r"\b", ev):
        return None
    m = re.search(r"(?i)\beach\W+(?:\w+\W+){0,3}?" + _VERB + r"\W+(?:\w+\W+){0,2}?(\d{1,2}(?:\.\d+)?)\s?%", ev)
    if m:
        return ("each", float(m.group(1)))
    m = re.search(r"\b" + nrx + r"\b((?:\W+\w+){0,10}?)\W+" + _VERB + r"\W+" + _PCT, ev)
    listed_before = m and re.search(r"(?:,|\band|\bor)\s*$", ev[:m.start()])  # "..., YouTube and Apple accounted for"
    if m and not listed_before and not re.search(r"(,\s*|\band\s+)[A-Z]", m.group(1)):  # nor ", Sony" after the name
        return ("single", float(m.group(2)))
    m = re.search(r"(?i)(?:largest|top|major|principal)\s+(?:\w+\s+){0,3}?(?:customers|accounts|clients|licensees)(?:\W+\w+){0,20}?\W+" + _PCT, ev)
    if m:
        return ("group", float(m.group(1)))
    return None


def is_resale(ev: str, names) -> bool:
    """'revenues from Apple products' = a reseller of Apple: Apple supplies it, not the other way round."""
    nrx = "(?:" + "|".join(re.escape(n) for n in names if n and len(n) >= 3) + ")"
    return bool(re.search(r"(?i)pre-owned|refurbished|\bresell|\breseller", ev) or
                re.search(r"\b" + nrx + r"(?:-branded|\s+(?:products|devices|branded|merchandise))", ev))


def describe_link(ticker, partner, rel, row, maps):
    """{statement, disclosed_by, share, share_kind, depends_on, invalid} from who filed the document and what it says."""
    by_cik, names = maps
    tn, pn = _short(names.get(ticker, ticker), ticker), _short(names.get(partner, partner), partner)
    st, url, ev = row.get("source_type"), str(row.get("source_url") or ""), str(row.get("evidence") or "")
    m = _CIK_RX.search(url)
    discloser = by_cik.get(int(m.group(1))) if (m and st == "filing") else None
    role = {"SUPPLIER": "supplier", "CUSTOMER": "customer", "COMPETITOR": "competitor"}[rel]
    named = lambda tk, nm: [nm, nm.split()[0], tk] + _SHORT.get(tk, [])  # noqa: E731
    out = {"disclosed_by": discloser, "share": None, "share_kind": None, "depends_on": None, "partner_name": pn, "invalid": False}

    def share_text(kind, v, holder):
        return {"single": f": about {v:g}% of {holder}'s revenue",
                "each": f": one of {holder}'s customers that each provided at least {v:g}% of revenue",
                "group": f": one of {holder}'s largest customers, which together provided {v:g}% of revenue"}[kind]

    if st == "filing" and discloser == partner and rel == "SUPPLIER":   # partner's filing names the target as its customer
        if is_resale(ev, named(ticker, tn)):
            out["invalid"] = True
        sh = share_of(ev, named(ticker, tn))
        statement = f"{pn}'s annual report names {tn} as a customer" + (share_text(*sh, pn) if sh else "") + "."
        if sh:
            out.update(share=sh[1], share_kind=sh[0], depends_on="partner_on_target")
    elif st == "filing" and discloser == partner:
        statement = f"{pn}'s annual report names {tn} as a {'supplier' if rel == 'CUSTOMER' else 'competitor'}."
    elif st == "filing" and discloser == ticker:
        sh = share_of(ev, named(partner, pn)) if rel == "CUSTOMER" else None
        statement = f"{tn}'s annual report names {pn} as a {role}" + (share_text(*sh, tn) if sh else "") + "."
        if sh:
            out.update(share=sh[1], share_kind=sh[0], depends_on="target_on_partner")
    elif st == "filing":
        statement = f"An SEC filing names {pn} as a {role} of {tn}."
    elif st == "news":
        statement = f"A news article reports {pn} as a {role} of {tn} (news, not an official filing)."
    else:
        statement = f"A {st or 'non-official'} source describes {pn} as a {role} of {tn} (not an official filing)."
    out["statement"] = statement
    return out


@router.get("/{ticker}/supply-chain")
def get_supply_chain(ticker: str, depth: int = 1, verified_only: bool = False):
    """Relationship graph. depth=2 adds second-order links (partners of partners).
    Every link carries its source, evidence quote, confidence and verification dates.
    verified_only=true hides links that are unverified (legacy) or stale."""
    ticker = ticker.upper()
    try:
        # Only links with a stored quote and source document are ever shown.
        evidence_filter = (" AND COALESCE(source_type,'legacy') <> 'legacy' AND COALESCE(TRIM(evidence),'') <> ''"
                           " AND COALESCE(TRIM(source_url),'') <> ''")
        status_filter = evidence_filter + (" AND COALESCE(status,'active')='active'" if verified_only else " AND COALESCE(status,'active')<>'rejected'")
        df = pd.read_sql(text("SELECT * FROM supply_chain WHERE ticker=:t" + status_filter), engine, params={"t": ticker})

        # Reverse links: rows where OTHER companies list this ticker as their partner.
        # If NVDA records AAPL as a CUSTOMER, then NVDA is a SUPPLIER to AAPL.
        rev = pd.read_sql(text("SELECT * FROM supply_chain WHERE partner_ticker=:t AND ticker<>:t" + status_filter),
                          engine, params={"t": ticker})
        if not rev.empty:
            flip = {"CUSTOMER": "SUPPLIER", "SUPPLIER": "CUSTOMER", "COMPETITOR": "COMPETITOR"}
            rev = rev.assign(partner_ticker=rev["ticker"], ticker=ticker,
                             relationship=rev["relationship"].map(lambda r: flip.get(normalize_relationship(r))),
                             inferred=True)
            df = pd.concat([df.assign(inferred=False), rev], ignore_index=True)
        if df.empty:
            return {"nodes": [], "links": [], "summary": {"active": 0, "unverified": 0, "stale": 0}}

        # Prefer the strongest evidence when the same partner appears twice
        df["_rank"] = df.get("source_rank", pd.Series([0] * len(df))).fillna(0)
        df = df.sort_values(["_rank", "confidence"], ascending=False, na_position="last")

        nodes = [{"id": ticker, "type": "TARGET"}]
        links = []
        seen_partners = {ticker}
        BLACKLIST = {"UNKNOWN", "NONE", "NULL", "TBA", "VARIOUS", "N/A"}
        summary = {"active": 0, "unverified": 0, "stale": 0}
        maps = _sec_maps()

        for _, row in df.iterrows():
            partner = row['partner_ticker']
            if not partner or str(partner).upper() in BLACKLIST or partner in seen_partners:
                continue
            rel = normalize_relationship(row['relationship'])
            if not rel:
                continue
            prov = _prov(row)
            meaning = describe_link(ticker, partner, rel, row, maps)
            if meaning["invalid"]:
                continue  # evidence contradicts the link direction (e.g. a reseller of the company's products)
            st = prov["status"] or "active"
            summary[st] = summary.get(st, 0) + 1
            inferred = bool(row.get('inferred', False))
            nodes.append({"id": partner, "type": rel, "depth": 1, "inferred": inferred, "status": st})
            seen_partners.add(partner)
            links.append({"source": ticker, "target": partner, "type": rel, "depth": 1, "inferred": inferred, **prov,
                          **meaning})

        if depth >= 2 and len(seen_partners) > 1:
            first = [p for p in seen_partners if p != ticker]
            placeholders = ", ".join(f":p{i}" for i in range(len(first)))
            q2 = text(f"SELECT * FROM supply_chain WHERE ticker IN ({placeholders}) AND partner_ticker <> :t" + status_filter)
            params = {f"p{i}": p for i, p in enumerate(first)}
            params["t"] = ticker
            df2 = pd.read_sql(q2, engine, params=params)
            seen_links = set()
            for _, row in df2.iterrows():
                src, partner = row['ticker'], row['partner_ticker']
                if not partner or str(partner).upper() in BLACKLIST or (src, partner) in seen_links:
                    continue
                seen_links.add((src, partner))
                rel = normalize_relationship(row['relationship'])
                if not rel:
                    continue
                prov = _prov(row)
                if partner not in seen_partners:
                    nodes.append({"id": partner, "type": rel, "depth": 2, "status": prov["status"] or "active"})
                    seen_partners.add(partner)
                links.append({"source": src, "target": partner, "type": rel, "depth": 2, **prov})

        conc = sorted([{"partner": l["target"], "name": l["partner_name"], "share": l["share"], "kind": l["share_kind"],
                        "direction": l["depends_on"]}
                       for l in links if l.get("depends_on") and l.get("share_kind") in ("single", "each")], key=lambda x: -x["share"])
        return {"nodes": nodes, "links": links, "summary": summary, "concentration": conc}
    except Exception as e:
        print(f"❌ supply-chain endpoint failed for {ticker}: {e}")
        return {"nodes": [], "links": [], "error": str(e)}
