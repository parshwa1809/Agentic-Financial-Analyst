"""
Retrieval-Augmented Generation store for Project Oracle.

  embeddings : Ollama, model `nomic-embed-text` (768-dim, free, runs locally)
  vector DB  : TiDB Cloud `rag_chunks` table. Uses TiDB's native VECTOR(768) column and
               VEC_COSINE_DISTANCE when the cluster supports it; otherwise stores the
               vector as JSON and ranks with NumPy (same results, a little slower).
  documents  : 10-K/20-F text, company profiles, news headlines, relationship evidence.
               Every chunk keeps its source URL and date so answers can cite it.
"""
import hashlib
import json
import math
import os
import re
from datetime import datetime
from typing import Dict, Iterable, List, Optional

import numpy as np
import requests
from sqlalchemy import text

from services.db_manager import get_engine

engine = get_engine()
_OLLAMA = os.getenv("OLLAMA_API_URL", "http://host.docker.internal:11434").split("/api/")[0].rstrip("/")
# EMBED_PROVIDER=ollama   → nomic-embed-text on your Mac (768-dim), table rag_chunks
# EMBED_PROVIDER=fastembed → BAAI/bge-small-en-v1.5 inside the container on CPU (384-dim), table rag_chunks_bge.
#                            No Ollama needed, so this is the free option for hosting.
EMBED_PROVIDER = os.getenv("EMBED_PROVIDER", "ollama").lower()
if EMBED_PROVIDER == "fastembed":
    EMBED_MODEL = os.getenv("FASTEMBED_MODEL", "BAAI/bge-small-en-v1.5")
    DIM = 384
    TABLE = "rag_chunks_bge"
else:
    EMBED_MODEL = os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text")
    DIM = int(os.getenv("OLLAMA_EMBED_DIM", "768"))
    TABLE = "rag_chunks"
_FE = {"model": None}
_MODE = {"native": None}  # True = TiDB VECTOR column, False = JSON fallback


# ----------------------------------------------------------------- schema
def ensure_table() -> bool:
    """Create rag_chunks if needed. Returns True when native vector search is available."""
    if _MODE["native"] is not None:
        return _MODE["native"]
    cols = """id BIGINT AUTO_INCREMENT PRIMARY KEY,
              ticker VARCHAR(20), doc_type VARCHAR(16), title VARCHAR(512), source_url TEXT,
              published_at DATETIME, chunk TEXT, content_hash CHAR(40) UNIQUE,
              created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
              INDEX (ticker, doc_type)"""
    with engine.begin() as conn:
        existing = conn.execute(text(
            "SELECT DATA_TYPE FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE() "
            "AND TABLE_NAME=:tbl AND COLUMN_NAME IN ('embedding','embedding_json')"), {"tbl": TABLE}).fetchall()
        if existing:
            _MODE["native"] = any(str(r[0]).lower().startswith("vector") for r in existing)
            return _MODE["native"]
        try:
            conn.execute(text(f"CREATE TABLE {TABLE} ({cols}, embedding VECTOR({DIM}))"))
            _MODE["native"] = True
            print(f"🧠 {TABLE} created with native TiDB VECTOR column")
        except Exception as e:
            print(f"🧠 Native VECTOR type unavailable ({str(e)[:80]}); using JSON vectors + NumPy ranking")
            conn.execute(text(f"CREATE TABLE IF NOT EXISTS {TABLE} ({cols}, embedding_json LONGTEXT)"))
            _MODE["native"] = False
    return _MODE["native"]


# ----------------------------------------------------------------- embeddings
def embed(texts: List[str], kind: str = "document") -> List[List[float]]:
    """Embed with Ollama. nomic-embed-text expects task prefixes for best retrieval."""
    if not texts:
        return []
    if EMBED_PROVIDER == "fastembed":
        try:
            from fastembed import TextEmbedding
        except ImportError as e:
            raise RuntimeError("EMBED_PROVIDER=fastembed needs `pip install --only-binary=:all: fastembed` "
                               "(see requirements-hosting.txt); use EMBED_PROVIDER=ollama locally") from e
        if _FE["model"] is None:
            _FE["model"] = TextEmbedding(model_name=EMBED_MODEL)
        items = [t[:4000] for t in texts]
        vecs = _FE["model"].query_embed(items) if kind == "query" else _FE["model"].embed(items)
        return [list(map(float, v)) for v in vecs]
    prefix = "search_query: " if kind == "query" else "search_document: "
    inputs = [prefix + t[:8000] for t in texts]
    try:
        res = requests.post(f"{_OLLAMA}/api/embed", json={"model": EMBED_MODEL, "input": inputs}, timeout=300)
        if res.status_code == 200 and res.json().get("embeddings"):
            return res.json()["embeddings"]
    except requests.RequestException:
        pass
    out = []  # older Ollama: one text per call
    for t in inputs:
        res = requests.post(f"{_OLLAMA}/api/embeddings", json={"model": EMBED_MODEL, "prompt": t}, timeout=120)
        res.raise_for_status()
        out.append(res.json()["embedding"])
    return out


def _vec_literal(v: Iterable[float]) -> str:
    return "[" + ",".join(f"{x:.6f}" for x in v) + "]"


# ----------------------------------------------------------------- chunking
def chunk_text(body: str, size: int = 1200, overlap: int = 150) -> List[str]:
    """Split on paragraph boundaries into ~size-char chunks with a little overlap."""
    paras = [p.strip() for p in re.split(r"\n\s*\n", body or "") if len(p.strip()) > 40]
    chunks, cur = [], ""
    for p in paras:
        if len(p) > size:  # very long paragraph: split by sentences
            for s in re.split(r"(?<=[.!?])\s+", p):
                if len(cur) + len(s) > size and cur:
                    chunks.append(cur.strip()); cur = cur[-overlap:] + " "
                cur += s + " "
            continue
        if len(cur) + len(p) > size and cur:
            chunks.append(cur.strip()); cur = cur[-overlap:] + "\n"
        cur += p + "\n\n"
    if len(cur.strip()) > 40:
        chunks.append(cur.strip())
    return chunks


# ----------------------------------------------------------------- write
def add_documents(docs: List[Dict], batch: int = 32) -> int:
    """docs: [{ticker, doc_type, title, source_url, published_at, chunk}]. Skips chunks already
    stored (content hash). Returns number of new chunks indexed."""
    native = ensure_table()
    for d in docs:
        d["content_hash"] = hashlib.sha1(f"{d['ticker']}|{d['doc_type']}|{d['chunk']}".encode()).hexdigest()
    if not docs:
        return 0
    hashes = [d["content_hash"] for d in docs]
    have = set()
    with engine.connect() as conn:
        for i in range(0, len(hashes), 500):
            part = hashes[i:i + 500]
            ph = ",".join(f":h{j}" for j in range(len(part)))
            have |= {r[0] for r in conn.execute(text(f"SELECT content_hash FROM {TABLE} WHERE content_hash IN ({ph})"),
                                                {f"h{j}": h for j, h in enumerate(part)})}
    new = [d for d in docs if d["content_hash"] not in have]
    col = "embedding" if native else "embedding_json"
    for i in range(0, len(new), batch):
        part = new[i:i + batch]
        vecs = embed([d["chunk"] for d in part])
        rows = [{**{k: d.get(k) for k in ("ticker", "doc_type", "title", "source_url", "published_at", "chunk", "content_hash")},
                 "v": _vec_literal(v) if native else json.dumps([round(x, 6) for x in v])} for d, v in zip(part, vecs)]
        with engine.begin() as conn:
            conn.execute(text(f"""INSERT IGNORE INTO {TABLE}
                (ticker, doc_type, title, source_url, published_at, chunk, content_hash, {col})
                VALUES (:ticker, :doc_type, :title, :source_url, :published_at, :chunk, :content_hash, :v)"""), rows)
    return len(new)


# ----------------------------------------------------------------- read
def search(query: str, ticker: Optional[str] = None, k: int = 8, doc_types: Optional[List[str]] = None) -> List[Dict]:
    """Top-k chunks for the query, optionally limited to a ticker (plus market-wide items)."""
    native = ensure_table()
    q = embed([query], kind="query")[0]
    where, params = [], {}
    if ticker:
        where.append("ticker IN (:t, 'MARKET')"); params["t"] = ticker.upper()
    if doc_types:
        where.append("doc_type IN (" + ",".join(f":d{i}" for i in range(len(doc_types))) + ")")
        params.update({f"d{i}": d for i, d in enumerate(doc_types)})
    w = (" WHERE " + " AND ".join(where)) if where else ""
    cols = "id, ticker, doc_type, title, source_url, published_at, chunk"
    with engine.connect() as conn:
        if native:
            params["q"] = _vec_literal(q)
            rows = conn.execute(text(f"SELECT {cols}, VEC_COSINE_DISTANCE(embedding, :q) AS dist FROM {TABLE}{w} "
                                     f"ORDER BY dist LIMIT {int(k * 3)}"), params).mappings().all()
            scored = [(1 - float(r["dist"]), dict(r)) for r in rows]
        else:
            rows = conn.execute(text(f"SELECT {cols}, embedding_json FROM {TABLE}{w}"), params).mappings().all()
            if not rows:
                return []
            m = np.array([json.loads(r["embedding_json"]) for r in rows], dtype=np.float32)
            qv = np.array(q, dtype=np.float32)
            sims = (m @ qv) / (np.linalg.norm(m, axis=1) * np.linalg.norm(qv) + 1e-9)
            top = np.argsort(-sims)[: k * 3]
            scored = [(float(sims[i]), {kk: v for kk, v in dict(rows[i]).items() if kk != "embedding_json"}) for i in top]
    # light recency boost for news so fresh headlines beat stale ones of similar relevance
    now = datetime.utcnow()
    out = []
    for sim, r in scored:
        bonus = 0.0
        if r.get("doc_type") == "news" and r.get("published_at"):
            age_days = max((now - r["published_at"]).days, 0) if isinstance(r["published_at"], datetime) else 30
            bonus = 0.05 * math.exp(-age_days / 7)
        r["score"] = round(sim + bonus, 4)
        r["published_at"] = str(r["published_at"]) if r.get("published_at") else None
        out.append(r)
    out.sort(key=lambda r: -r["score"])
    return out[:k]


def stats(ticker: Optional[str] = None) -> Dict:
    ensure_table()
    with engine.connect() as conn:
        q = f"SELECT doc_type, COUNT(*), MAX(created_at) FROM {TABLE}" + (" WHERE ticker=:t" if ticker else "") + " GROUP BY doc_type"
        rows = conn.execute(text(q), {"t": ticker.upper()} if ticker else {}).fetchall()
    return {"vector_search": "TiDB native VECTOR" if _MODE["native"] else "JSON + NumPy",
            "embedding_model": EMBED_MODEL, "table": TABLE,
            "by_type": {r[0]: {"chunks": int(r[1]), "last_indexed": str(r[2])} for r in rows},
            "total": sum(int(r[1]) for r in rows)}
