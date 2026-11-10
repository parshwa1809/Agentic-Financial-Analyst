"""Checks that numbers in an AI-written answer actually appear in the material it was given."""
import re

NUM = re.compile(r"(?<![\w\[])\$?\d[\d,]*(?:\.\d+)?\s?(?:%|percent|billion|million|trillion|bn|[BMT]\b)?", re.I)
_MULT = {"thousand": 1e3, "million": 1e6, "m": 1e6, "billion": 1e9, "bn": 1e9, "b": 1e9, "trillion": 1e12, "t": 1e12}


def _value(tok: str):
    """(value, decimals, multiplier) of a number token like '$47.1 billion' or '2.91%'."""
    m = re.search(r"\d[\d,]*(?:\.\d+)?", tok)
    if not m:
        return None, 0, 1
    raw = m.group(0).replace(",", "")
    unit = re.sub(r"[^a-z]", "", tok.lower().split(raw[-1], 1)[-1]) if raw else ""
    return float(raw), (len(raw.split(".")[1]) if "." in raw else 0), _MULT.get(unit, 1)


def unsupported_numbers(answer: str, context: str):
    """Numbers in `answer` not found in `context`, allowing rounding and unit changes
    (28.5 ← 28.45; $47.1 billion ← $47,061 million; but 3.1% is not 2.91%)."""
    ctx_vals = []
    for m in NUM.finditer(context or ""):
        v, _, mult = _value(m.group(0))
        if v is not None:
            ctx_vals += [v, v * mult]
    flagged = []
    for m in NUM.finditer(answer or ""):
        tok = m.group(0).strip()
        val, dec, mult = _value(tok)
        if val is None:
            continue
        if ("%" not in tok and "$" not in tok and val <= 10 and dec == 0) or (1900 <= val <= 2100 and dec == 0):
            continue  # small counts and years
        tol = 0.5 * 10 ** (-dec) + 1e-9
        if not any(abs(val - c) <= tol or abs(val * mult - c) <= tol * mult for c in ctx_vals):
            flagged.append(tok)
    return sorted(set(flagged))
