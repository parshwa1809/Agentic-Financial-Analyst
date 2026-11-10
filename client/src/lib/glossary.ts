// Shared plain-language glossary. Same definitions the backend uses in app/internal/glossary.py,
// fetched once from /api/research/glossary and cached for the session.
import { useEffect, useState } from 'react';
import { api } from '@/lib/api';

export interface GlossaryTerm { key: string; term: string; match: string[]; short: string; more: string }
export interface Glossary { byKey: Record<string, GlossaryTerm>; lookup: (word: string) => GlossaryTerm | undefined; re: RegExp | null }

const EMPTY: Glossary = { byKey: {}, lookup: () => undefined, re: null };
let cache: Glossary | null = null;
let pending: Promise<Glossary> | null = null;

const esc = (s: string) => s.replace(/[.*+?^${}()|[\]\\/]/g, '\\$&');

function build(terms: GlossaryTerm[]): Glossary {
  const byKey: Record<string, GlossaryTerm> = {};
  const byWord = new Map<string, GlossaryTerm>();
  for (const t of terms) {
    byKey[t.key] = t;
    for (const m of t.match) if (!byWord.has(m.toLowerCase())) byWord.set(m.toLowerCase(), t);
  }
  // longest spellings first so "gross profit" wins over "profit", "diluted EPS" over "EPS"
  const words = [...byWord.keys()].sort((a, b) => b.length - a.length);
  const re = words.length ? new RegExp(`(?<![\\w/-])(${words.map(esc).join('|')})(?![\\w/-])`, 'gi') : null;
  return { byKey, re, lookup: (w) => byWord.get(w.toLowerCase()) };
}

export function loadGlossary(): Promise<Glossary> {
  if (cache) return Promise.resolve(cache);
  if (!pending) {
    pending = api.getGlossary()
      .then((r) => (cache = build(r.data.terms || [])))
      .catch(() => { pending = null; return EMPTY; });
  }
  return pending;
}

export function useGlossary(): Glossary {
  const [g, setG] = useState<Glossary>(cache || EMPTY);
  useEffect(() => {
    let alive = true;
    if (!cache) loadGlossary().then((x) => alive && setG(x));
    return () => { alive = false; };
  }, []);
  return g;
}
