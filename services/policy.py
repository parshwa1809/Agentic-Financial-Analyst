"""
Output policy: Oracle reports facts; it does not advise.

`enforce(text)` finds sentences that give a recommendation, rating, price target,
valuation opinion or prediction, removes them, and returns what was removed so it
can be logged on the AI-quality page. Text inside quotation marks is exempt
(a filing may legitimately be quoted), and so are company names/terms such as
"buyback" or "selling, general and administrative" because the patterns below
only match advice phrasing.

This is a rule check, not an AI judgement: every pattern is listed here and has a test.
"""
import re
from typing import Dict, List, Tuple

PATTERNS: List[Tuple[str, str]] = [
    ("rating", r"\b(strong\s+)?(buy|sell|hold|outperform|underperform|overweight|underweight)\s+(rating|recommendation|signal|call)\b"),
    ("rating", r"\b(rate|rated|rating)\s+(it|the stock|shares|[A-Z]{1,5})\s+(a\s+)?(buy|sell|hold)\b"),
    ("rating", r"\b(verdict|decision)\s*[:\-]?\s*(buy|sell|hold)\b"),
    ("recommendation", r"\b(i|we)\s+(would\s+)?(recommend|suggest|advise)\b"),
    ("recommendation", r"\bmy\s+recommendation\b|\bour\s+recommendation\b"),
    ("recommendation", r"\b(you|investors|one)\s+(should|could|might want to|may want to|ought to|need to)\s+"
                       r"(buy|sell|hold|consider\s+(buying|selling)|invest|accumulate|avoid|reduce|trim|add\s+to|exit|short)\b"),
    ("recommendation", r"\b(good|great|attractive|compelling|solid|bad|poor|risky)\s+(investment|buy|entry\s+point|opportunity\s+to\s+buy|stock\s+to\s+(buy|own))\b"),
    ("recommendation", r"\b(accumulate|go\s+long|go\s+short|take\s+profits?|buy\s+the\s+dip|on\s+dips)\b"),
    ("valuation_opinion", r"\b(undervalued|overvalued|under-valued|over-valued|fairly\s+valued|cheap\s+stock|expensive\s+stock)\b"),
    ("valuation_opinion", r"\b(price\s+target|target\s+price|fair\s+value|intrinsic\s+value)\b"),
    ("valuation_opinion", r"\b(upside|downside)\s+(potential|of\s+\d)"),
    ("prediction", r"\b(will\s+(likely|probably)|(is|are)\s+(likely|expected|poised|set)\s+to|should|could\s+soon)\s+"
                   r"(rise|fall|rally|surge|soar|drop|plunge|climb|decline|rebound|outperform|underperform|go\s+(up|down)|double|beat\s+the\s+market)\b"),
    ("prediction", r"\b(bullish|bearish)\b"),
]
_COMPILED = [(k, re.compile(p, re.I)) for k, p in PATTERNS]
_QUOTED = re.compile(r"“[^”]*”|\"[^\"]*\"")
_SENT = re.compile(r"(?<=[.!?])\s+(?=[A-Z\[(*•-])|\n+")


def find(text: str) -> List[Dict]:
    """All policy hits in text (quoted passages ignored)."""
    bare = _QUOTED.sub(" ", text or "")
    hits = []
    for kind, rx in _COMPILED:
        for m in rx.finditer(bare):
            hits.append({"kind": kind, "phrase": m.group(0)})
    return hits


def enforce(text: str) -> Tuple[str, List[Dict]]:
    """Drop every sentence that breaks the policy. Returns (clean_text, removed)."""
    if not text:
        return text, []
    parts = _SENT.split(text)
    seps = _SENT.findall(text)
    kept, removed = [], []
    for i, sentence in enumerate(parts):
        hits = find(sentence)
        if hits:
            removed.append({"sentence": sentence.strip()[:300], "kinds": sorted({h["kind"] for h in hits}),
                            "phrases": [h["phrase"] for h in hits][:5]})
            continue
        kept.append(sentence + (seps[i] if i < len(seps) else ""))
    clean = "".join(kept).strip()
    if removed:
        clean = (clean + "\n\n" if clean else "") + (
            f"({len(removed)} sentence{'s' if len(removed) > 1 else ''} removed: Oracle reports facts only and does not "
            "give ratings, recommendations, price targets or predictions.)")
    return clean, removed


def enforce_list(items: List[str]) -> Tuple[List[str], List[Dict]]:
    out, removed = [], []
    for it in items:
        if find(it):
            removed.append({"sentence": str(it)[:300], "kinds": sorted({h["kind"] for h in find(it)}),
                            "phrases": [h["phrase"] for h in find(it)][:5]})
        else:
            out.append(it)
    return out, removed
