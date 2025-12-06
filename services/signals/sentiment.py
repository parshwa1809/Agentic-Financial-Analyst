def analyze_sentiment(title: str) -> float:
    title = title.lower()
    pos = ["surges", "jumps", "beats", "bull", "record", "upgrade", "gains", "buy", "soars", "profit"]
    neg = ["plunges", "drops", "misses", "bear", "crash", "downgrade", "losses", "sell", "falls", "risk"]
    
    score = 0
    for w in pos: 
        if w in title: score += 1
    for w in neg: 
        if w in title: score -= 1
    return score