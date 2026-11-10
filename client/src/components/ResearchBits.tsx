import { useEffect, useRef, useState, type ReactNode, type ElementType } from 'react';
import { useSearchParams } from 'react-router-dom';
import { Search, ExternalLink, AlertTriangle, Loader2 } from 'lucide-react';
import { useWatchlist } from '@/hooks/useWatchlist';

/**
 * Selected ticker for the research pages, kept in the URL (?t=KO) and tied to the watchlist:
 * opens on the first watchlist ticker, and if the selected ticker is removed from the
 * watchlist it moves to the next one automatically.
 */
export function useWatchlistTicker() {
  const wl = useWatchlist();
  const [ticker, setTicker] = useResearchTicker('');
  const prev = useRef<string[]>([]);
  useEffect(() => {
    if (!wl.loaded) return;
    const wasListed = prev.current.includes(ticker);
    if ((!ticker || (wasListed && !wl.symbols.includes(ticker))) && wl.symbols.length) setTicker(wl.symbols[0]);
    prev.current = wl.symbols;
  }, [wl.loaded, wl.symbols, ticker]); // eslint-disable-line react-hooks/exhaustive-deps
  return { ticker, setTicker, wl };
}

/** Ticker kept in the URL (?t=KO) so every research page shares it and links are shareable. */
export function useResearchTicker(fallback = '') {
  const [params, setParams] = useSearchParams();
  const ticker = (params.get('t') || fallback).toUpperCase();
  const setTicker = (t: string) => {
    const next = new URLSearchParams(params);
    next.set('t', t.toUpperCase());
    setParams(next, { replace: true });
  };
  return [ticker, setTicker] as const;
}

export function PageHeader({ icon: Icon, title, subtitle, children }: { icon: ElementType; title: string; subtitle: string; children?: ReactNode }) {
  return (
    <div className="flex flex-wrap items-end justify-between gap-4">
      <div>
        <div className="flex items-center gap-2 text-2xl font-bold tracking-tight"><Icon className="text-primary" /> {title}</div>
        <p className="text-sm text-muted-foreground mt-1 max-w-2xl">{subtitle}</p>
      </div>
      {children}
    </div>
  );
}

export function TickerInput({ value, onSubmit, placeholder = 'Ticker, e.g. KO' }: { value: string; onSubmit: (t: string) => void; placeholder?: string }) {
  const [draft, setDraft] = useState(value);
  useEffect(() => setDraft(value), [value]);
  return (
    <form onSubmit={(e) => { e.preventDefault(); if (draft.trim()) onSubmit(draft.trim().toUpperCase()); }}
      className="flex items-center gap-2 rounded-xl border border-border/70 bg-card/70 pl-3 pr-1 py-1">
      <Search size={15} className="text-muted-foreground" />
      <input value={draft} onChange={(e) => setDraft(e.target.value.toUpperCase())} placeholder={placeholder}
        className="bg-transparent outline-none font-mono font-bold text-sm w-24 uppercase" aria-label="Ticker symbol" />
      <button className="rounded-lg bg-primary text-primary-foreground text-xs font-semibold px-3 py-1.5">Load</button>
    </form>
  );
}

export function Stat({ label, value, hint, tone = '' }: { label: ReactNode; value: ReactNode; hint?: ReactNode; tone?: string }) {
  return (
    <div className="rounded-xl border border-border/70 bg-background/40 px-3 py-2.5">
      <div className="text-[10px] uppercase tracking-wider text-muted-foreground">{label}</div>
      <div className={`font-mono font-bold text-lg mt-0.5 ${tone}`}>{value}</div>
      {hint && <div className="text-[11px] text-muted-foreground mt-0.5">{hint}</div>}
    </div>
  );
}

export function Loading({ text = 'Pulling filings and prices…' }: { text?: string }) {
  return <div className="panel p-10 grid place-items-center text-muted-foreground text-sm gap-3"><Loader2 className="animate-spin text-primary" />{text}</div>;
}

export function ErrorBox({ message }: { message: string }) {
  return (
    <div className="panel p-4 flex gap-3 items-start border-destructive/40">
      <AlertTriangle className="text-destructive shrink-0" size={18} />
      <div className="text-sm">{message}</div>
    </div>
  );
}

export function Sources({ items }: { items?: Array<{ label: string; url: string }> }) {
  if (!items?.length) return null;
  return (
    <div className="panel p-4">
      <div className="text-xs font-semibold mb-2">Sources — every number above can be checked here</div>
      <ul className="grid md:grid-cols-2 gap-1.5 text-xs">
        {items.map((s) => (
          <li key={s.url}><a href={s.url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1.5 text-info hover:underline"><ExternalLink size={12} />{s.label}</a></li>
        ))}
      </ul>
    </div>
  );
}

export function Tabs<T extends string>({ tabs, value, onChange }: { tabs: Array<{ key: T; label: string }>; value: T; onChange: (t: T) => void }) {
  return (
    <div className="flex flex-wrap gap-1 rounded-xl bg-background/60 border border-border/70 p-1 w-fit">
      {tabs.map((t) => (
        <button key={t.key} onClick={() => onChange(t.key)} data-tab={t.key}
          className={`px-3 py-1.5 text-xs font-semibold rounded-lg transition-colors ${value === t.key ? 'bg-primary text-primary-foreground' : 'text-muted-foreground hover:text-foreground'}`}>{t.label}</button>
      ))}
    </div>
  );
}

export const LEVEL_CLS: Record<string, string> = {
  High: 'bg-destructive/15 text-destructive', Medium: 'bg-warning/15 text-warning', Low: 'bg-success/15 text-success',
};
