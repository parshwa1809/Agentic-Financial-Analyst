import sys, os, json, requests, time
import yfinance as yf
from services.db_manager import execute_query
from services.heartbeat import beat

# --- IMPORT SEARCH HUB ---
from services.search_engine_hub import search_web_unlimited

# --- CONFIG ---
def get_ollama_url():
    base = os.getenv("OLLAMA_API_URL", "http://host.docker.internal:11434")
    if base.endswith("/"): base = base[:-1]
    if not base.endswith("/api/generate"): base += "/api/generate"
    return base

OLLAMA_URL = get_ollama_url()
MODEL = os.getenv("OLLAMA_MODEL_NAME", "llama3") 

# ==========================================
# Evidence-backed relationship research
# ------------------------------------------
# Sources, strongest first:
#   1. the company's latest 10-K / 20-F on SEC EDGAR      (source_type "filing")
#   2. its Yahoo Finance business profile                  (source_type "profile")
#   3. web search results, only if 1+2 found little        (source_type "web")
# The LLM must return an exact quote for every partner. A link is saved only if
# that quote is really in the source text, the company resolves to a listed
# ticker, and the relationship is SUPPLIER / CUSTOMER / COMPETITOR.
# The old "internal LLM memory" fallback is gone: it produced unverifiable links.
# ==========================================
import re
from services.relationship_store import resolve, grounded, save_link, maintenance
from services.sec_filings import relationship_passages


def clean_json_string(text):
    text = text.replace("```json", "").replace("```", "").strip()
    start = text.find("{")
    end = text.rfind("}") + 1
    if start != -1 and end > start:
        return text[start:end]
    return text


EXTRACT_PROMPT = """You extract business relationships from a source document about {ticker} ({name}).

List every OTHER company that the text explicitly names as one of:
- SUPPLIER: sells goods/services/licences TO {ticker}
- CUSTOMER: buys from {ticker} (includes distributors and bottlers that buy from it)
- COMPETITOR: competes with {ticker}

Rules:
- Only companies NAMED in the text. Never use outside knowledge.
- "quote" must be copied word-for-word from the text and must contain the company's name.
- Skip generic groups ("various suppliers", "retailers") and {ticker} itself.
- If the text names no other company in one of these roles, return {{"partners": []}}. An empty list is a good answer.

Return JSON only: {{"partners": [{{"company": "<name exactly as written in the text>", "type": "SUPPLIER|CUSTOMER|COMPETITOR", "quote": "<exact sentence from the text that contains that name>"}}]}}

TEXT:
\"\"\"{context}\"\"\"
"""


def ask_llm(ticker, name, context):
    from services import llm
    prompt = EXTRACT_PROMPT.format(ticker=ticker, name=name, context=context[:24000])
    try:
        data = llm.generate_json(prompt, purpose="relationships", temperature=0, max_tokens=1500, timeout=240)
        items = data.get("partners", []) if isinstance(data, dict) else []
        return [i for i in items if isinstance(i, dict)]
    except Exception as e:
        print(f"      ⚠️ LLM extraction skipped: {e}")
        return []


def gather_sources(ticker):
    """Yield (source_type, source_url, llm_context, grounding_text, label)."""
    filing = relationship_passages(ticker)
    if filing and filing.get("text"):
        yield ("filing", filing["url"], filing["text"], filing.get("full_text") or filing["text"],
               f"{filing['form']} filed {filing['filed']}")
    try:
        summary = yf.Ticker(ticker).info.get("longBusinessSummary", "") or ""
    except Exception:
        summary = ""
    if len(summary) > 80:
        yield ("profile", f"https://finance.yahoo.com/quote/{ticker}/profile", summary, summary, "Yahoo profile")


def web_sources(ticker, name):
    query = f"{name} {ticker} major suppliers customers competitors"
    try:
        blob = search_web_unlimited(query, max_results=5) or ""
    except Exception as e:
        print(f"      ⚠️ Search failed: {e}")
        return
    for block in blob.split("SOURCE: ")[1:]:
        m = re.search(r"\((https?://[^)]+)\)", block)
        content = block.split("CONTENT:", 1)[-1].strip()
        if m and len(content) > 60:
            yield ("web", m.group(1), content, content, "web result")


# ---------------------------------------------------------------- deterministic (no AI)
_ROLE_RX = {
    "COMPETITOR": re.compile(r"\b(compet\w*|rival\w*)\b", re.I),
    "SUPPLIER": re.compile(r"\b(suppliers?|supplied by|sole[- ]source|single[- ]source|purchases? \w+ from|"
                           r"contract manufactur\w*|we (?:buy|purchase|source) \w+(?: \w+){0,4} from|foundr\w+)\b", re.I),
    "CUSTOMER": re.compile(r"\b(customers?|accounted for \d|bottl\w+ partners?|distributors?)\b", re.I),
}
_NOT_PARTNER = re.compile(r"\b(acqui\w+|merger|lawsuit|plaintiff|defendant|litigation|joint venture|subsidiar\w+|"
                          r"indenture|trustee|underwriter|auditor|credit agreement|lender)\b", re.I)


def deterministic_links(ticker, filing):
    """Links from the company's OWN annual report without any AI call: a sentence must name a
    listed company AND contain role words (compete / supplier / customer). Returns saved count."""
    from services.sec_filings import ORG
    text = filing.get("full_text") or filing.get("text") or ""
    saved, seen = 0, set()
    for sent in re.split(r"(?<=[.;])\s+", text):
        if not (40 < len(sent) < 700) or _NOT_PARTNER.search(sent):
            continue
        roles = [r for r, rx in _ROLE_RX.items() if rx.search(sent)]
        if len(roles) != 1:          # ambiguous sentence (e.g. "customers and competitors"): skip, never guess
            continue
        for org in {o.strip(" ,") for o in ORG.findall(sent)}:
            partner = resolve(org)
            if not partner or partner == ticker or (partner, roles[0]) in seen:
                continue
            quote = re.sub(r"\s+", " ", sent).strip()
            if save_link(ticker, partner, roles[0], "filing", quote, filing["url"]):
                seen.add((partner, roles[0]))
                saved += 1
                print(f"      🔗 {ticker} —{roles[0]}→ {partner}  [own {filing['form']}, rule-based]")
    return saved


def _llm_done(url):
    try:
        from services.redis_manager import get_redis_client
        return bool(get_redis_client().get(f"rel:llm_done:{url}"))
    except Exception:
        return False


def _mark_llm_done(url):
    try:
        from services.redis_manager import get_redis_client
        get_redis_client().set(f"rel:llm_done:{url}", "1", ex=45 * 86400)
    except Exception:
        pass


def _note_rejected(ticker, company, reason):
    """Keep the last 50 rejected proposals so the AI-quality page can show why links were not saved."""
    try:
        from services.redis_manager import get_redis_client
        rc = get_redis_client()
        rc.lpush("rel:rejected", json.dumps({"ticker": ticker, "company": company[:80], "reason": reason, "at": time.strftime("%Y-%m-%d %H:%M")}))
        rc.ltrim("rel:rejected", 0, 49)
    except Exception:
        pass


def research_source(ticker, name, src):
    stype, url, ctx, ground, label = src
    found = ask_llm(ticker, name, ctx)
    stats = {"proposed": len(found), "saved": 0, "unlisted": 0, "ungrounded": 0, "bad_type": 0}
    for item in found:
        company = str(item.get("company") or item.get("partner") or "").strip()
        partner = resolve(company)
        if not partner or partner == ticker:
            stats["unlisted"] += 1
            _note_rejected(ticker, company, "same company" if partner == ticker else "not a US-listed company")
            continue
        quote = str(item.get("quote") or "")
        if not grounded(quote, ground, must_mention=(company, partner)):
            stats["ungrounded"] += 1
            _note_rejected(ticker, company, "quote not found in the source")
            continue
        if save_link(ticker, partner, item.get("type"), stype, quote, url):
            stats["saved"] += 1
            print(f"      🔗 {ticker} —{str(item.get('type')).upper()}→ {partner}  [{label}]")
        else:
            stats["bad_type"] += 1
    print(f"      📊 {label}: {stats}")
    try:  # relationship funnel for the AI-quality page
        from services.redis_manager import get_redis_client
        rc = get_redis_client()
        for k, v in stats.items():
            if v:
                rc.incrby(f"rel:{k}", v)
    except Exception:
        pass
    return stats["saved"]


def discover_partners(ticker):
    """Research one ticker and save only evidence-backed links. Returns number saved."""
    ticker = ticker.upper()
    print(f"🕵️‍♂️ Deep Dive: researching {ticker}...")
    try:
        name = yf.Ticker(ticker).info.get("shortName") or ticker
    except Exception:
        name = ticker
    saved = 0
    # 1) Suppliers' own filings naming this company as a customer (deterministic, no LLM)
    try:
        from services.sec_filings import customer_disclosures
        for d in customer_disclosures(ticker):
            if save_link(d["supplier"], ticker, "CUSTOMER", "filing", d["quote"], d["url"]):
                saved += 1
                print(f"      🔗 {d['supplier']} supplies {ticker}  [supplier's 10-K, filed {d.get('filed')}]")
    except Exception as e:
        print(f"      ⚠️ customer-disclosure search failed: {e}")
    # 2) This company's own annual report: rule-based first (free), then the LLM once per filing.
    #    Profile and web sources are not used: they are unofficial and cost AI calls.
    filing = relationship_passages(ticker)
    if filing and filing.get("text"):
        saved += deterministic_links(ticker, filing)
        if not _llm_done(filing["url"]):
            saved += research_source(ticker, name, ("filing", filing["url"], filing["text"],
                                                    filing.get("full_text") or filing["text"], f"{filing['form']} filed {filing['filed']}"))
            _mark_llm_done(filing["url"])
        else:
            # Same filing as last time: what it says has not changed, so its links stay confirmed.
            execute_query("UPDATE supply_chain SET last_verified=NOW(), status='active' WHERE source_url=:u", {"u": filing["url"]})
            print(f"      ⏭️  {filing['form']} already read by the AI; links from it re-confirmed without a new AI call")
    print(f"✅ Deep Dive complete for {ticker}: {saved} evidence-backed links saved/confirmed")
    try:  # lets the maintenance worker know this ticker was researched recently
        from services.redis_manager import get_redis_client
        get_redis_client().set(f"research:last:{ticker}", str(int(time.time())), ex=7 * 86400)
    except Exception:
        pass
    return saved


def run_continuous_cycle():
    print(f"♾️   Starting Bidirectional Supply Chain Worker...")

    while True:
        try:
            print("\n🔄  Starting New Research Cycle...")
            # This fetches ALL active tickers to continuously update them
            maintenance()
            rows = execute_query("SELECT symbol FROM tickers WHERE is_active=1")
            tickers = [r[0] for r in rows] if rows else []
            
            from services.redis_manager import get_redis_client
            _rc = get_redis_client()
            cycle_s = float(os.getenv("RESEARCH_CYCLE_HOURS", "24" if os.getenv("LLM_PROVIDER", "ollama") != "ollama" else "1")) * 3600
            for ticker in tickers:
                last = _rc.get(f"research:last:{ticker}")
                if last and time.time() - int(last) < cycle_s * 0.9:
                    print(f"   ⏭️  {ticker} researched recently, skipping")
                    continue
                discover_partners(ticker)
                time.sleep(5)

            beat("supply_chain_agent", "ok", f"researched {len(tickers)} tickers", ttl=int(float(os.getenv("RESEARCH_CYCLE_HOURS", "24" if os.getenv("LLM_PROVIDER", "ollama") != "ollama" else "1")) * 3600 * 2 + 3600))
            hours = float(os.getenv("RESEARCH_CYCLE_HOURS", "24" if os.getenv("LLM_PROVIDER", "ollama") != "ollama" else "1"))
            print(f"💤  Cycle Complete. Sleeping {hours:g} h...")
            time.sleep(int(hours * 3600))
            
        except KeyboardInterrupt: break
        except Exception as e:
            print(f"⚠️  Worker crashed: {e}. Restarting in 30s...")
            beat("supply_chain_agent", "error", str(e))
            time.sleep(30)

if __name__ == "__main__":
    run_continuous_cycle()