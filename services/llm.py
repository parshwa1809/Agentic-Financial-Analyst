"""
One place for every LLM call in Oracle.

  LLM_PROVIDER=groq    → Groq's free tier (OpenAI-compatible API), default model llama-3.3-70b-versatile.
                         Needs GROQ_API_KEY in .env. Falls back to local Ollama when the daily
                         budget is used up or Groq is unreachable (LLM_FALLBACK=ollama, the default).
  LLM_PROVIDER=ollama  → local Ollama on your Mac (free, offline, no limits).

Free tiers cap requests per day, so every call names its `purpose` and is counted against a
daily budget in Redis (see BUDGETS). When a budget is spent, generate() raises BudgetExceeded;
workers skip that cycle and the chat tells the user, instead of failing silently.
"""
import json
import os
import re
import time
from datetime import datetime, timezone

import requests

from services.redis_manager import get_redis_client

_r = get_redis_client()

PROVIDER = os.getenv("LLM_PROVIDER", "ollama").lower()
FALLBACK = os.getenv("LLM_FALLBACK", "ollama").lower()
GROQ_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
OLLAMA_BASE = os.getenv("OLLAMA_API_URL", "http://host.docker.internal:11434").split("/api/")[0].rstrip("/")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL_NAME", "phi3:mini")

# Daily request budgets per purpose for metered providers (Groq free tier ≈ 1,000 requests/day).
BUDGETS = {
    "chat": int(os.getenv("LLM_BUDGET_CHAT", "350")),
    "news": int(os.getenv("LLM_BUDGET_NEWS", "200")),
    "relationships": int(os.getenv("LLM_BUDGET_RELATIONSHIPS", "200")),
    "council": int(os.getenv("LLM_BUDGET_COUNCIL", "120")),
    "other": int(os.getenv("LLM_BUDGET_OTHER", "50")),
}
TOTAL_BUDGET = int(os.getenv("LLM_DAILY_BUDGET", "900"))


class LLMError(Exception):
    pass


class BudgetExceeded(LLMError):
    pass


def metered() -> bool:
    return PROVIDER != "ollama"


def model_name() -> str:
    return f"{GROQ_MODEL} (Groq)" if PROVIDER == "groq" else f"{OLLAMA_MODEL} (Ollama)"


def _day() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def usage() -> dict:
    day = _day()
    out = {"provider": PROVIDER, "model": model_name(), "day_utc": day, "budgets": {}}
    total = 0
    for p, cap in BUDGETS.items():
        n = int(_r.get(f"llm:used:{day}:{p}") or 0)
        total += n
        out["budgets"][p] = {"used": n, "cap": cap}
    out["total"] = {"used": total, "cap": TOTAL_BUDGET}
    return out


def _take(purpose: str):
    if not metered():
        return
    day, p = _day(), purpose if purpose in BUDGETS else "other"
    key, tkey = f"llm:used:{day}:{p}", f"llm:used:{day}:total"
    used, total = int(_r.get(key) or 0), int(_r.get(tkey) or 0)
    if used >= BUDGETS[p] or total >= TOTAL_BUDGET:
        raise BudgetExceeded(f"Daily {p} budget reached ({used}/{BUDGETS[p]}, total {total}/{TOTAL_BUDGET}). Resets at 00:00 UTC.")
    pipe = _r.pipeline()
    pipe.incr(key); pipe.expire(key, 2 * 86400); pipe.incr(tkey); pipe.expire(tkey, 2 * 86400)
    pipe.execute()


def _groq(prompt, system, json_mode, temperature, max_tokens, timeout):
    if not GROQ_KEY:
        raise LLMError("GROQ_API_KEY is not set in .env")
    body = {"model": GROQ_MODEL, "temperature": temperature, "max_tokens": max_tokens,
            "messages": ([{"role": "system", "content": system}] if system else []) + [{"role": "user", "content": prompt}]}
    if json_mode:
        body["response_format"] = {"type": "json_object"}
    for attempt in range(3):
        res = requests.post(GROQ_URL, json=body, timeout=timeout, headers={"Authorization": f"Bearer {GROQ_KEY}"})
        if res.status_code == 429:  # per-minute limit: wait as told, then retry
            wait = float(res.headers.get("retry-after", 2 + attempt * 3))
            time.sleep(min(wait, 20))
            continue
        if res.status_code != 200:
            raise LLMError(f"Groq HTTP {res.status_code}: {res.text[:200]}")
        return res.json()["choices"][0]["message"]["content"]
    raise LLMError("Groq rate limit: retries exhausted")


def _ollama(prompt, system, json_mode, temperature, max_tokens, timeout):
    body = {"model": OLLAMA_MODEL, "prompt": (system + "\n\n" if system else "") + prompt, "stream": False,
            "options": {"temperature": temperature, "num_predict": max_tokens}}
    if json_mode:
        body["format"] = "json"
    res = requests.post(f"{OLLAMA_BASE}/api/generate", json=body, timeout=timeout)
    if res.status_code != 200:
        raise LLMError(f"Ollama HTTP {res.status_code}: {res.text[:200]}")
    return res.json().get("response", "")


def generate(prompt: str, *, purpose: str = "other", system: str = None, json_mode: bool = False,
             temperature: float = 0.1, max_tokens: int = 1200, timeout: int = 180) -> str:
    """Return the model's text. Raises BudgetExceeded / LLMError when nothing can answer."""
    if PROVIDER == "groq":
        try:
            _take(purpose)
            return _groq(prompt, system, json_mode, temperature, max_tokens, timeout)
        except (BudgetExceeded, LLMError, requests.RequestException) as e:
            if FALLBACK != "ollama":
                raise
            try:
                return _ollama(prompt, system, json_mode, temperature, max_tokens, timeout)
            except Exception:
                raise e if isinstance(e, LLMError) else LLMError(str(e))
    return _ollama(prompt, system, json_mode, temperature, max_tokens, timeout)


def generate_json(prompt: str, **kw) -> dict:
    """generate() in JSON mode, tolerant of code fences and stray text around the object."""
    text = generate(prompt, json_mode=True, **kw)
    text = text.replace("```json", "").replace("```", "").strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", text, re.S)
        if m:
            try:
                return json.loads(m.group(0))
            except json.JSONDecodeError:
                pass
    return {}
