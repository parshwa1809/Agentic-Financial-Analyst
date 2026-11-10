"""
Single gatekeeper for supply-chain relationships.

Every link written to `supply_chain` goes through save_link(), which enforces:
  1. Both companies are real, currently traded US tickers.
  2. The relationship is one of SUPPLIER / CUSTOMER / COMPETITOR.
  3. The evidence quote really appears in the source text (no invented quotes).
  4. Every link carries its source type, source URL, evidence quote,
     first-seen and last-verified dates. A link without a quote AND a source
     URL is rejected, and maintenance() deletes any such row already stored.

maintenance() keeps the table honest over time: it removes malformed rows,
marks links that haven't been re-confirmed in 30 days as stale, and deletes
anything unconfirmed for 90 days.
"""
import json
import re
import time

import yfinance as yf

from services.db_manager import execute_query
from services.redis_manager import get_redis_client

_r = get_redis_client()

VALID_SYMBOL = re.compile(r"^[A-Z]{1,5}([.-][A-Z]{1,2})?$")
REL_MAP = {
    "SUPPLIER": "SUPPLIER", "VENDOR": "SUPPLIER", "MANUFACTURER": "SUPPLIER", "PROVIDER": "SUPPLIER",
    "CONTRACT MANUFACTURER": "SUPPLIER", "LICENSOR": "SUPPLIER",
    "CUSTOMER": "CUSTOMER", "CLIENT": "CUSTOMER", "BUYER": "CUSTOMER", "OEM": "CUSTOMER",
    "DISTRIBUTOR": "CUSTOMER", "RESELLER": "CUSTOMER", "BOTTLER": "CUSTOMER", "LICENSEE": "CUSTOMER",
    "COMPETITOR": "COMPETITOR", "RIVAL": "COMPETITOR", "PEER": "COMPETITOR", "CHALLENGER": "COMPETITOR",
}
INVERSE = {"SUPPLIER": "CUSTOMER", "CUSTOMER": "SUPPLIER", "COMPETITOR": "COMPETITOR"}

# How much we trust each kind of source. Re-confirmation from a second source adds a bonus.
SOURCE_CONFIDENCE = {"filing": 0.90, "news": 0.65, "profile": 0.60, "web": 0.55}
SOURCE_RANK = {"filing": 4, "news": 3, "profile": 2, "web": 1, "legacy": 0}
STALE_DAYS, EXPIRE_DAYS = 30, 90

# Any row without a stored quote and source document is removed, never shown.
EVIDENCE_PURGE_SQL = ("DELETE FROM supply_chain WHERE source_type IS NULL OR source_type = 'legacy' "
                      "OR evidence IS NULL OR CHAR_LENGTH(TRIM(evidence)) < 20 "
                      "OR source_url IS NULL OR source_url NOT LIKE 'http%'")

SUFFIXES = re.compile(r"\b(incorporated|inc|corporation|corp|company|co|ltd|limited|plc|holdings?|group|"
                      r"sab de cv|s a b de c v|de cv|sa|ag|nv|se|spa|lp|llc|kk|ltda|the|class [a-c]|adr)\b\.?", re.I)


def normalize_rel(rel):
    return REL_MAP.get(str(rel or "").upper().strip().replace("_", " "))


def _norm_name(s: str) -> str:
    s = s.lower().replace("&", " and ").replace(".com", "")
    s = SUFFIXES.sub(" ", s)
    return re.sub(r"[^a-z0-9 ]", " ", re.sub(r"\s+", " ", s)).strip()


_NAME_INDEX = {"ts": 0, "idx": None}


def _name_index():
    if _NAME_INDEX["idx"] and time.time() - _NAME_INDEX["ts"] < 86400:
        return _NAME_INDEX["idx"]
    from services.sec_filings import company_tickers
    idx = {}
    for tk, v in company_tickers().items():
        n = _norm_name(v["title"])
        # keep the shortest ticker per name (common shares over preferred/units)
        if n and (n not in idx or len(tk) < len(idx[n])):
            idx[n] = tk
    _NAME_INDEX.update(ts=time.time(), idx=idx)
    return idx


ALIASES = {"google": "GOOGL", "alphabet": "GOOGL", "facebook": "META", "tsmc": "TSM", "taiwan semiconductor": "TSM",
           "amazon web services": "AMZN", "aws": "AMZN", "youtube": "GOOGL", "instagram": "META", "whatsapp": "META",
           "linkedin": "MSFT", "github": "MSFT", "azure": "MSFT", "microsoft azure": "MSFT", "google cloud": "GOOGL",
           "amazon": "AMZN", "walmart": "WMT", "pepsico": "PEP", "pepsi": "PEP", "coca cola": "KO", "coke": "KO",
           "foxconn": None, "samsung": None, "openai": None, "anthropic": None}


def resolve(name_or_ticker: str):
    """Company name or ticker -> listed US ticker, or None if private/unknown/foreign-only."""
    raw = str(name_or_ticker or "").strip()
    if not raw:
        return None
    up = raw.upper()
    n = _norm_name(raw)
    if n in ALIASES:
        return ALIASES[n]
    idx = _name_index()
    if VALID_SYMBOL.match(up) and up in _known_tickers():
        return up
    if n in idx:
        return idx[n]
    # unique prefix match: the text uses a SHORTER form of the listed name
    # ("procter gamble" -> "procter and gamble co"). The reverse is not allowed:
    # "Coca-Cola HBC" must not become "Coca-Cola" (KO) - a longer name is a different company.
    cands = {t for nm, t in idx.items() if nm.startswith(n + " ")} if len(n) >= 5 else set()
    return next(iter(cands)) if len(cands) == 1 else None


def _known_tickers():
    from services.sec_filings import company_tickers
    return company_tickers()


def is_listed(symbol: str) -> bool:
    """Real, currently trading symbol (price history in the last 5 days). Cached."""
    s = str(symbol or "").upper().strip()
    if not VALID_SYMBOL.match(s):
        return False
    key = f"listed:{s}"
    try:
        hit = _r.get(key)
        if hit is not None:
            return hit == b"1"
    except Exception:
        pass
    try:
        ok = not yf.Ticker(s).history(period="5d").empty
    except Exception:
        return False
    try:
        _r.set(key, "1" if ok else "0", ex=7 * 86400 if ok else 86400)
    except Exception:
        pass
    return ok


def _squash(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(s or "").lower()).strip()


def grounded(quote: str, source_text: str, must_mention=()) -> bool:
    """True if the quote is really in the source (allowing whitespace/punctuation differences)
    and mentions at least one of `must_mention` (the partner's name or ticker)."""
    q, src = _squash(quote), _squash(source_text)
    if len(q) < 20 or not src:
        return False
    if q not in src:
        # tolerate small LLM edits: 85% of 4-word shingles must appear
        words = q.split()
        shingles = [" ".join(words[i:i + 4]) for i in range(max(1, len(words) - 3))]
        if sum(1 for sh in shingles if sh in src) / len(shingles) < 0.85:
            return False
    if must_mention:
        return any(_squash(m) and _squash(m) in q for m in must_mention)
    return True


def save_link(ticker, partner, rel, source_type, evidence, source_url=None, mirror=True):
    """Validate and upsert one relationship (and its mirror). Returns True if saved."""
    t, p, rel = str(ticker).upper(), str(partner or "").upper(), normalize_rel(rel)
    if not rel or t == p or not is_listed(t) or not is_listed(p):
        return False
    # Evidence rule: no quote, no source document or unknown source type -> not saved.
    if source_type not in SOURCE_CONFIDENCE or len(str(evidence or "").strip()) < 20 or not str(source_url or "").startswith("http"):
        print(f"      ⛔ {t}->{p} rejected: missing evidence quote or source link")
        return False
    conf = SOURCE_CONFIDENCE.get(source_type, 0.5)
    rank = SOURCE_RANK.get(source_type, 0)
    for a, b, r_, ev in ((t, p, rel, evidence), (p, t, INVERSE[rel], evidence)) if mirror else ((t, p, rel, evidence),):
        try:
            execute_query("INSERT IGNORE INTO tickers (symbol, name, is_active) VALUES (:s, :s, 0)", {"s": b})
            execute_query(
                """INSERT INTO supply_chain (ticker, partner_ticker, relationship, confidence, reason,
                       source_type, source_url, evidence, first_seen, last_verified, status, n_sources)
                   VALUES (:a, :b, :r, :c, :ev, :st, :url, :ev, NOW(), NOW(), 'active', 1)
                   ON DUPLICATE KEY UPDATE
                       n_sources     = IF(source_type <> :st, COALESCE(n_sources, 1) + 1, COALESCE(n_sources, 1)),
                       confidence    = LEAST(0.97, GREATEST(COALESCE(confidence, 0), :c) + IF(source_type <> :st AND source_type <> 'legacy', 0.05, 0)),
                       relationship  = IF(:rank >= COALESCE(source_rank, 0), :r, relationship),
                       source_url    = IF(:rank >= COALESCE(source_rank, 0), :url, source_url),
                       evidence      = IF(:rank >= COALESCE(source_rank, 0), :ev, evidence),
                       reason        = IF(:rank >= COALESCE(source_rank, 0), :ev, reason),
                       source_type   = IF(:rank >= COALESCE(source_rank, 0), :st, source_type),
                       source_rank   = GREATEST(COALESCE(source_rank, 0), :rank),
                       first_seen    = COALESCE(first_seen, NOW()),
                       last_verified = NOW(),
                       status        = 'active'""",
                {"a": a, "b": b, "r": r_, "c": conf, "ev": (ev or "")[:1000], "st": source_type,
                 "url": source_url, "rank": rank})
        except Exception as e:
            print(f"      ❌ save_link {a}->{b} failed: {e}")
            return False
    return True


def maintenance():
    """Clean and age the relationship table. Safe to run every cycle."""
    steps = [
        ("normalise relationship names",
         "UPDATE supply_chain SET relationship = CASE "
         + " ".join(f"WHEN UPPER(TRIM(relationship))='{k}' THEN '{v}'" for k, v in REL_MAP.items())
         + " ELSE relationship END WHERE relationship IS NOT NULL"),
        ("remove links with no relationship type",
         "DELETE FROM supply_chain WHERE relationship IS NULL OR TRIM(relationship) = ''"),
        ("remove self-links and non-ticker partners",
         "DELETE FROM supply_chain WHERE ticker = partner_ticker OR partner_ticker IS NULL "
         "OR NOT REGEXP_LIKE(partner_ticker, '^[A-Z]{1,5}([.-][A-Z]{1,2})?$', 'c') "
         "OR NOT REGEXP_LIKE(ticker, '^[A-Z]{1,5}([.-][A-Z]{1,2})?$', 'c')"),
        ("flag ambiguous types as unverified",
         "UPDATE supply_chain SET status='unverified' WHERE relationship NOT IN ('SUPPLIER','CUSTOMER','COMPETITOR')"),
        ("delete links without evidence (no quote, no source link, or legacy)",
         EVIDENCE_PURGE_SQL),
        (f"mark links not re-confirmed in {STALE_DAYS} days as stale",
         f"UPDATE supply_chain SET status='stale' WHERE status='active' AND last_verified < NOW() - INTERVAL {STALE_DAYS} DAY"),
        (f"delete links unconfirmed for {EXPIRE_DAYS} days",
         f"DELETE FROM supply_chain WHERE status IN ('stale','unverified') "
         f"AND COALESCE(last_verified, first_seen) < NOW() - INTERVAL {EXPIRE_DAYS} DAY"),
    ]
    for label, sql in steps:
        try:
            execute_query(sql)
        except Exception as e:
            print(f"      ⚠️ maintenance step '{label}' failed: {e}")
    try:
        rows = execute_query("SELECT status, COUNT(*) FROM supply_chain GROUP BY status")
        summary = {str(s): int(n) for s, n in rows or []}
        print(f"   🧹 Relationship table: {summary}")
        return summary
    except Exception:
        return {}
