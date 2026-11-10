import { useEffect, useRef, useState } from 'react';
import { Plus, Search, Star, ChevronDown } from 'lucide-react';
import type { WatchItem } from '@/hooks/useWatchlist';

interface Props {
  items: WatchItem[];
  loaded: boolean;
  value: string;
  onChange: (t: string) => void;
  onAdd?: (t: string) => Promise<void>;
  compact?: boolean;
}

/**
 * Ticker switcher shared by the research pages. It always mirrors the watchlist:
 *  - up to 8 tickers: chips that wrap onto a second line if needed
 *  - more than 8: one scrollable row of chips plus a "Jump to" menu, so the header never grows
 *  - any other ticker can still be typed in, and added to the watchlist with one click
 */
export default function WatchlistTabs({ items, loaded, value, onChange, onAdd, compact }: Props) {
  const [draft, setDraft] = useState('');
  const [adding, setAdding] = useState(false);
  const many = items.length > 8;
  const inList = items.some((i) => i.symbol === value);
  const strip = useRef<HTMLDivElement>(null);

  // keep the selected chip visible in the scrolling row
  useEffect(() => {
    strip.current?.querySelector<HTMLElement>(`[data-ticker="${value}"]`)?.scrollIntoView({ block: 'nearest', inline: 'nearest' });
  }, [value, items.length]);

  return (
    <div className={`flex flex-wrap items-center gap-2 ${compact ? '' : 'panel px-3 py-2.5'}`}>
      <span className="text-[11px] uppercase tracking-wider text-muted-foreground flex items-center gap-1.5 shrink-0">
        <Star size={12} /> Watchlist {loaded && <span className="font-mono">({items.length})</span>}
      </span>

      <div ref={strip} className={`flex gap-1.5 min-w-0 ${many ? 'flex-1 overflow-x-auto scroll-panel pb-1' : 'flex-wrap'}`}
        style={many ? { maskImage: 'linear-gradient(90deg, #000 92%, transparent)' } : undefined}>
        {items.map((t) => (
          <button key={t.symbol} data-ticker={t.symbol} onClick={() => onChange(t.symbol)} title={t.name}
            className={`shrink-0 rounded-lg px-2.5 py-1 text-xs font-bold font-mono border transition-colors ${
              t.symbol === value ? 'bg-primary/15 border-primary/60 text-foreground' : 'bg-card/70 border-border/70 text-muted-foreground hover:text-foreground hover:border-primary/40'}`}>
            {t.symbol}
          </button>
        ))}
        {loaded && items.length === 0 && <span className="text-xs text-muted-foreground">Empty — add tickers on the Watchlist page or below.</span>}
      </div>

      {many && (
        <label className="relative shrink-0">
          <select value={inList ? value : ''} onChange={(e) => e.target.value && onChange(e.target.value)} aria-label="Jump to ticker"
            className="appearance-none rounded-lg bg-background/60 border border-border/70 pl-2.5 pr-7 py-1 text-xs font-mono">
            <option value="">Jump to…</option>
            {items.map((t) => <option key={t.symbol} value={t.symbol}>{t.symbol}{t.name && t.name !== t.symbol ? ` · ${t.name}` : ''}</option>)}
          </select>
          <ChevronDown size={12} className="absolute right-2 top-1/2 -translate-y-1/2 pointer-events-none text-muted-foreground" />
        </label>
      )}

      <form onSubmit={(e) => { e.preventDefault(); if (draft.trim()) { onChange(draft.trim().toUpperCase()); setDraft(''); } }}
        className="flex items-center gap-1.5 rounded-lg border border-border/70 bg-background/40 pl-2 pr-1 py-0.5 shrink-0">
        <Search size={12} className="text-muted-foreground" />
        <input value={draft} onChange={(e) => setDraft(e.target.value.toUpperCase())} placeholder="Other ticker" aria-label="Other ticker"
          className="bg-transparent outline-none font-mono text-xs w-20 uppercase py-0.5" />
      </form>

      {!inList && value && onAdd && (
        <button disabled={adding} onClick={async () => { setAdding(true); try { await onAdd(value); } finally { setAdding(false); } }}
          className="shrink-0 flex items-center gap-1 rounded-lg bg-primary/15 text-primary text-xs font-semibold px-2.5 py-1 hover:bg-primary/25 disabled:opacity-60">
          <Plus size={12} /> {adding ? 'Adding…' : `Add ${value} to watchlist`}
        </button>
      )}
    </div>
  );
}
