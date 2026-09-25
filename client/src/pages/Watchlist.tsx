import { useState, useEffect } from 'react';
import { api } from '@/lib/api';
import { Search, Plus, X, Loader2, Check, Database, Newspaper, Network, Radio } from 'lucide-react';

interface Ticker { symbol: string; name: string; is_active?: boolean | number; price?: number; change?: number }

const JOBS = [
  { icon: Database, label: 'Backfill 30 days of 5-min bars' },
  { icon: Newspaper, label: 'Fetch + score latest news' },
  { icon: Network, label: 'Map supply chain with the LLM agent' },
  { icon: Radio, label: 'Join the live price stream' },
];

export default function Watchlist() {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<Ticker[]>([]);
  const [selected, setSelected] = useState<Record<string, boolean>>({});
  const [active, setActive] = useState<Ticker[]>([]);
  const [loading, setLoading] = useState(false);
  const [pipeline, setPipeline] = useState<{ symbols: string[]; step: number } | null>(null);

  const fetchActive = async () => {
    try { setActive((await api.getActiveTickers()).data); } catch (e) { console.error(e); }
  };
  const loadUniverse = async () => {
    setLoading(true);
    try { setResults((await api.getAllTickers()).data); } catch (e) { console.error(e); }
    setLoading(false);
  };
  const search = async (q = query) => {
    if (!q) return loadUniverse();
    setLoading(true);
    try { setResults((await api.searchTickers(q)).data); } catch (e) { console.error(e); }
    setLoading(false);
  };

  useEffect(() => { fetchActive(); loadUniverse(); }, []);

  const picked = Object.keys(selected).filter((s) => selected[s]);
  const isActive = (s: string) => active.some((a) => a.symbol === s);

  const activate = async () => {
    if (!picked.length) return;
    setPipeline({ symbols: picked, step: 0 });
    for (const s of picked) {
      try { await api.activateTicker(s); } catch (e) { console.error(`Failed to activate ${s}`, e); }
    }
    for (let i = 1; i <= JOBS.length; i++) {
      await new Promise((r) => setTimeout(r, 450));
      setPipeline({ symbols: picked, step: i });
    }
    setSelected({});
    await fetchActive();
    await search();
  };

  const deactivate = async (s: string) => {
    await api.deactivateTicker(s);
    await fetchActive();
  };

  return (
    <div className="space-y-5">
      <div>
        <div className="text-2xl font-bold tracking-tight">Watchlist</div>
        <p className="text-sm text-muted-foreground mt-1">Add a ticker and the background agents start collecting prices, news and supply-chain data for it.</p>
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-[minmax(0,1fr)_360px] gap-5">
        <div className="panel p-4">
          <div className="flex gap-2">
            <div className="flex-1 flex items-center gap-2 rounded-xl bg-background/60 border border-border/80 px-3 focus-within:border-primary">
              <Search size={16} className="text-muted-foreground" />
              <input data-tour="search" className="flex-1 bg-transparent py-2.5 text-sm focus:outline-none placeholder:text-muted-foreground"
                placeholder="Search a symbol or company (e.g. AMD, Palantir)" value={query}
                onChange={(e) => { setQuery(e.target.value); search(e.target.value); }} />
              {loading && <Loader2 size={16} className="animate-spin text-muted-foreground" />}
            </div>
            <button data-tour="activate" onClick={activate} disabled={!picked.length || !!(pipeline && pipeline.step < JOBS.length)}
              className="rounded-xl px-4 text-sm font-semibold flex items-center gap-2 bg-primary text-primary-foreground disabled:bg-muted disabled:text-muted-foreground transition-colors">
              <Plus size={16} /> Add {picked.length ? `(${picked.length})` : ''}
            </button>
          </div>

          <div className="mt-4 overflow-y-auto scroll-panel max-h-[520px] space-y-1.5">
            {results.map((r) => {
              const on = !!selected[r.symbol], act = isActive(r.symbol);
              return (
                <button key={r.symbol} data-row={r.symbol} disabled={act} onClick={() => setSelected((p) => ({ ...p, [r.symbol]: !p[r.symbol] }))}
                  className={`w-full flex items-center gap-3 rounded-xl border px-3 py-2.5 text-left transition-all ${
                    on ? 'border-primary/60 bg-primary/10' : 'border-border/60 bg-background/40 hover:border-primary/30'} ${act ? 'opacity-70 cursor-default' : ''}`}>
                  <span className={`grid place-items-center w-5 h-5 rounded-md border ${on ? 'bg-primary border-primary text-white' : 'border-border'}`}>{on && <Check size={13} />}</span>
                  <span className="font-mono font-bold w-16">{r.symbol}</span>
                  <span className="flex-1 text-sm text-muted-foreground">{r.name}</span>
                  {act ? <span className="text-xs font-semibold text-success bg-success/10 rounded-full px-2 py-0.5">● Watching</span>
                    : <span className="text-xs text-muted-foreground">Not watched</span>}
                </button>
              );
            })}
            {!loading && results.length === 0 && <div className="text-center text-muted-foreground py-10 text-sm">No matches for “{query}”.</div>}
          </div>
        </div>

        <div className="space-y-5">
          {pipeline && (
            <div className="panel p-4 fade-up" data-tour="pipeline">
              <div className="text-[11px] uppercase tracking-wider text-muted-foreground">Queued for {pipeline.symbols.join(', ')}</div>
              <div className="mt-3 space-y-2.5">
                {JOBS.map((j, i) => {
                  const done = pipeline.step > i;
                  return (
                    <div key={j.label} className="flex items-center gap-2.5 text-sm">
                      <span className={`grid place-items-center w-7 h-7 rounded-lg transition-colors ${done ? 'bg-success/15 text-success' : 'bg-secondary text-muted-foreground'}`}>
                        {done ? <Check size={14} /> : pipeline.step === i ? <Loader2 size={14} className="animate-spin" /> : <j.icon size={14} />}
                      </span>
                      <span className={done ? '' : 'text-muted-foreground'}>{j.label}</span>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          <div className="panel p-4">
            <div className="flex items-center justify-between mb-3">
              <div className="font-semibold">Watching</div>
              <span className="chip text-muted-foreground">{active.length} tickers</span>
            </div>
            <div className="space-y-1.5">
              {active.map((t) => (
                <div key={t.symbol} className="fade-up flex items-center gap-3 rounded-xl bg-background/40 border border-border/60 px-3 py-2">
                  <div className="flex-1 leading-tight">
                    <div className="font-mono font-bold">{t.symbol}</div>
                    <div className="text-[11px] text-muted-foreground">{t.name}</div>
                  </div>
                  {typeof t.price === 'number' && (
                    <div className="text-right font-mono text-xs leading-tight">
                      <div>${t.price.toFixed(2)}</div>
                      <div className={t.change! >= 0 ? 'text-success' : 'text-destructive'}>{t.change! >= 0 ? '+' : ''}{t.change!.toFixed(2)}%</div>
                    </div>
                  )}
                  <button onClick={() => deactivate(t.symbol)} className="p-1.5 rounded-lg text-muted-foreground hover:text-destructive hover:bg-destructive/10"><X size={15} /></button>
                </div>
              ))}
              {active.length === 0 && <p className="text-sm text-muted-foreground text-center py-6">Nothing yet — add a ticker.</p>}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
