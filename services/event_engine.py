"""
Event engine: turns raw data into "what changed" alerts for the watchlist, each with evidence.

Every EVENT_CYCLE_SECONDS (default 10 min) it checks:
  1. Supply-chain moves — a verified supplier/customer of a watchlist company moved ≥ EVENT_MOVE_PCT
     in a day → alert on the watchlist company, quoting the 10-K / article that proves the link.
  2. Own price moves — a watchlist company itself moved ≥ EVENT_MOVE_PCT.
  3. New SEC filings — 8-K, 10-Q, 10-K, 6-K, 20-F filed by a watchlist company or a verified partner.
  4. Earnings — a report date within the next 7 days.
Events are de-duplicated by a key, stored in `oracle_events`, and shown in Alerts & brief.
"""
import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from sqlalchemy import text

from services.db_manager import get_engine, execute_query
from services.heartbeat import beat

engine = get_engine()
MOVE = float(os.getenv("EVENT_MOVE_PCT", "3")) / 100
CYCLE = int(os.getenv("EVENT_CYCLE_SECONDS", "600"))
FORMS = {"8-K": "warn", "10-Q": "info", "10-K": "info", "6-K": "info", "20-F": "info"}

DDL = """CREATE TABLE IF NOT EXISTS oracle_events (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    ticker VARCHAR(20), kind VARCHAR(24), severity VARCHAR(8), title VARCHAR(300), body TEXT,
    evidence_json TEXT, dedupe_key VARCHAR(190) UNIQUE, event_time DATETIME,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP, read_at DATETIME NULL,
    INDEX idx_events_time (created_at), INDEX idx_events_ticker (ticker))"""


def ensure_table():
    execute_query(DDL)


def emit(ticker, kind, severity, title, body, evidence=None, key=None, when=None):
    try:
        execute_query(
            "INSERT IGNORE INTO oracle_events (ticker, kind, severity, title, body, evidence_json, dedupe_key, event_time) "
            "VALUES (:t, :k, :s, :ti, :b, :e, :d, :w)",
            {"t": ticker, "k": kind, "s": severity, "ti": title[:300], "b": body, "e": json.dumps(evidence or {}, default=str),
             "d": (key or f"{kind}:{ticker}:{title}")[:190], "w": when or datetime.utcnow()})
    except Exception as e:
        print(f"⚠️ emit failed: {e}")


def watchlist():
    with engine.connect() as conn:
        return [r[0] for r in conn.execute(text("SELECT symbol FROM tickers WHERE is_active=1")).fetchall()]


def verified_links(tickers):
    """{watch_ticker: [(partner, relationship, evidence, url, source_type)]}"""
    out = {t: [] for t in tickers}
    if not tickers:
        return out
    ph = ",".join(f":t{i}" for i in range(len(tickers)))
    with engine.connect() as conn:
        rows = conn.execute(text(
            f"SELECT ticker, partner_ticker, relationship, evidence, source_url, source_type FROM supply_chain "
            f"WHERE ticker IN ({ph}) AND status='active' AND COALESCE(source_type,'legacy') <> 'legacy'"),
            {f"t{i}": t for i, t in enumerate(tickers)}).fetchall()
    for t, p, rel, ev, url, st in rows:
        out[t].append((p, rel, ev, url, st))
    return out


def daily_moves(symbols):
    """{symbol: (pct_change, last_close, date)} from daily closes (Yahoo, cached 1 h)."""
    from app.internal.research_data import get_prices
    out = {}
    if not symbols:
        return out
    px = get_prices(sorted(set(symbols)), years=1)
    for s in symbols:
        if s in px:
            c = px[s].dropna()
            if len(c) >= 2:
                out[s] = (float(c.iloc[-1] / c.iloc[-2] - 1), float(c.iloc[-1]), str(c.index[-1].date()))
    return out


def check_moves(wl, links):
    partners = {p for ls in links.values() for p, *_ in ls}
    moves = daily_moves(list(set(wl) | partners))
    for t in wl:
        if t in moves and abs(moves[t][0]) >= MOVE:
            chg, px, d = moves[t]
            emit(t, "price_move", "warn" if abs(chg) < 2 * MOVE else "high",
                 f"{t} {'rose' if chg > 0 else 'fell'} {abs(chg) * 100:.1f}% on {d}",
                 f"Closed at ${px:.2f}, a {chg * 100:+.1f}% move in one session.", {"change": chg, "close": px, "date": d},
                 key=f"move:{t}:{d}")
        for p, rel, ev, url, st in links.get(t, []):
            if p in moves and abs(moves[p][0]) >= MOVE:
                chg, px, d = moves[p]
                role = {"SUPPLIER": "supplier", "CUSTOMER": "customer", "COMPETITOR": "competitor"}.get(str(rel).upper(), "partner")
                emit(t, f"{role}_move", "warn" if abs(chg) < 2 * MOVE else "high",
                     f"{t}'s {role} {p} {'rose' if chg > 0 else 'fell'} {abs(chg) * 100:.1f}%",
                     f"{p} closed at ${px:.2f} ({chg * 100:+.1f}%) on {d}. The link is documented in the evidence below.",
                     {"partner": p, "relationship": rel, "change": chg, "date": d, "quote": ev, "url": url, "source_type": st},
                     key=f"pmove:{t}:{p}:{d}")


def check_filings(wl, links):
    from services.sec_filings import company_tickers, _get
    ct = company_tickers()
    partners = {p for ls in links.values() for p, *_ in ls}
    since = (datetime.utcnow() - timedelta(days=3)).strftime("%Y-%m-%d")
    owners = {}
    for t in wl:
        owners.setdefault(t, set()).add(t)
    for t, ls in links.items():
        for p, *_ in ls:
            owners.setdefault(p, set()).add(t)
    for sym in sorted(set(wl) | partners):
        info = ct.get(sym)
        if not info:
            continue
        try:
            rec = _get(f"https://data.sec.gov/submissions/CIK{info['cik']:010d}.json").json()["filings"]["recent"]
        except Exception:
            continue
        for form, date, acc, doc, items in zip(rec.get("form", []), rec.get("filingDate", []), rec.get("accessionNumber", []),
                                               rec.get("primaryDocument", []), rec.get("items", [""] * len(rec.get("form", [])))):
            if date < since:
                break
            if form not in FORMS:
                continue
            url = f"https://www.sec.gov/Archives/edgar/data/{info['cik']}/{acc.replace('-', '')}/{doc}"
            for owner in owners.get(sym, {sym}):
                own = owner == sym
                emit(owner, "filing", FORMS[form],
                     f"{sym} filed a {form}" + ("" if own else f" ({sym} is linked to {owner})"),
                     f"Filed {date}." + (f" 8-K items: {items}." if form == "8-K" and items else ""),
                     {"form": form, "filed": date, "url": url, "filer": sym, "items": items}, key=f"filing:{owner}:{acc}")


def check_earnings(wl):
    import yfinance as yf
    today = datetime.utcnow().date()
    for t in wl:
        try:
            cal = yf.Ticker(t).calendar or {}
            dates = cal.get("Earnings Date") or []
        except Exception:
            continue
        for d in dates[:1]:
            d = d if hasattr(d, "year") else None
            if d and 0 <= (d - today).days <= 7:
                emit(t, "earnings", "info", f"{t} reports earnings on {d:%a %b %d}",
                     f"Results expected in {(d - today).days} day(s). Expect higher volatility around the report.",
                     {"date": str(d), "source": "Yahoo Finance calendar"}, key=f"earn:{t}:{d}")


def check_news(wl, links):
    rel = {t: {p for p, *_ in ls} for t, ls in links.items()}
    watch = set(wl) | {p for s in rel.values() for p in s}
    if not watch:
        return
    ph = ",".join(f":s{i}" for i in range(len(watch)))
    with engine.connect() as conn:
        rows = conn.execute(text(
            f"SELECT id, ticker, headline, url, risk_score, risk_factor, published_at FROM news_articles WHERE ticker IN ({ph}) "
            f"AND risk_score >= 60 AND published_at >= NOW() - INTERVAL 2 DAY"), {f"s{i}": s for i, s in enumerate(watch)}).fetchall()
    for nid, sym, head, url, risk, cat, pub in rows:
        targets = [sym] if sym in wl else [t for t, ps in rel.items() if sym in ps]
        for t in targets:
            emit(t, "news_risk", "high" if risk >= 80 else "warn",
                 f"High-risk news: {head[:140]}" if t == sym else f"High-risk news about {t}'s partner {sym}",
                 f"AI risk score {risk}/100 ({cat}). {head}", {"url": url, "risk": risk, "category": cat, "subject": sym, "published": pub},
                 key=f"news:{t}:{nid}")


def scan():
    ensure_table()
    wl = watchlist()
    links = verified_links(wl)
    # Only sourced facts: price moves (market data), SEC filings, earnings dates. (AI-scored news risk removed.)
    for name, fn in (("moves", lambda: check_moves(wl, links)), ("filings", lambda: check_filings(wl, links)),
                     ("earnings", lambda: check_earnings(wl))):
        try:
            fn()
        except Exception as e:
            print(f"⚠️ {name} check failed: {e}")
    with engine.connect() as conn:
        n = conn.execute(text("SELECT COUNT(*) FROM oracle_events WHERE created_at >= NOW() - INTERVAL 1 DAY")).scalar()
    return int(n or 0)


if __name__ == "__main__":
    print("🔔 Event engine started")
    time.sleep(20)
    while True:
        try:
            n = scan()
            beat("event_engine", "ok", f"{n} events in the last 24 h", ttl=CYCLE * 3)
        except Exception as e:
            print(f"❌ event engine: {e}")
            beat("event_engine", "error", str(e), ttl=CYCLE * 3)
        time.sleep(CYCLE)
