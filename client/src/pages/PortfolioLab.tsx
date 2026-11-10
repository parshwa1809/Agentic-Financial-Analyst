/* eslint-disable @typescript-eslint/no-explicit-any */
import { useEffect, useState } from 'react';
import { ResponsiveContainer, PieChart, Pie, Cell, Tooltip, ScatterChart, Scatter, XAxis, YAxis, CartesianGrid, LabelList } from 'recharts';
import { PieChart as PieIcon, Play, Plus, Trash2, Info, RefreshCw, Link2 } from 'lucide-react';
import { api } from '@/lib/api';
import { Def } from '@/components/PlainText';
import { pct, signedPct, num, money, usd, errMsg } from '@/lib/format';
import { PageHeader, Stat, ErrorBox, Loading } from '@/components/ResearchBits';
import { useWatchlist } from '@/hooks/useWatchlist';

const COLORS = ['hsl(248 92% 68%)', 'hsl(152 70% 46%)', 'hsl(190 92% 50%)', 'hsl(38 96% 58%)', 'hsl(350 89% 62%)', 'hsl(280 80% 66%)', 'hsl(90 60% 50%)', 'hsl(20 90% 60%)', 'hsl(210 20% 70%)', 'hsl(330 80% 66%)', 'hsl(60 80% 55%)', 'hsl(170 60% 45%)'];

type Row = { ticker: string; weight: number; why: string };

/** Equal weights across the watchlist, rounded to whole percents that sum to 100. */
const fromWatchlist = (symbols: string[], names: Record<string, string | undefined>): Row[] => {
  const n = symbols.length;
  if (!n) return [];
  const base = Math.floor(100 / n);
  return symbols.map((t, i) => ({ ticker: t, weight: base + (i < 100 - base * n ? 1 : 0), why: names[t] && names[t] !== t ? `Watchlist · ${names[t]}` : 'Watchlist holding' }));
};

export default function PortfolioLab() {
  const wl = useWatchlist();
  const [rows, setRows] = useState<Row[]>([]);
  const [synced, setSynced] = useState(true);   // follows the watchlist until you edit the mix
  const names = Object.fromEntries(wl.items.map((i) => [i.symbol, i.name]));
  const wlKey = wl.symbols.join(',');
  useEffect(() => {
    if (synced) { setRows(fromWatchlist(wl.symbols, names)); setRes(null); }
  }, [wlKey, synced]); // eslint-disable-line react-hooks/exhaustive-deps
  const edit = (next: Row[]) => { setSynced(false); setRows(next); };
  const [budget, setBudget] = useState(100000);
  const [years, setYears] = useState(3);
  const [res, setRes] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const total = rows.reduce((s, r) => s + (+r.weight || 0), 0);

  const run = async () => {
    setLoading(true); setError('');
    try {
      const r = await api.analyzePortfolio({
        tickers: rows.map((r) => r.ticker.trim().toUpperCase()).filter(Boolean),
        weights: Object.fromEntries(rows.map((r) => [r.ticker.trim().toUpperCase(), (+r.weight || 0) / (total || 1)])),
        budget, years,
      });
      setRes(r.data);
    } catch (e) { setError(errMsg(e)); }
    setLoading(false);
  };

  const why = Object.fromEntries(rows.map((r) => [r.ticker.toUpperCase(), r.why]));
  const scatter = res ? [
    ...res.holdings.map((h: any) => ({ name: h.ticker, x: h.annual_volatility * 100, y: h.annual_return * 100, kind: 'asset' })),
  ] : [];
  const portPoints = res ? [
    { name: 'Your mix', x: res.portfolio.volatility * 100, y: res.portfolio.expected_return * 100 },
  ] : [];

  return (
    <div className="space-y-5">
      <PageHeader icon={PieIcon} title="Portfolio Lab"
        subtitle="Pick a mix of your watchlist stocks and see how that mix behaved in the past: how much it went up or down, how much it swung, and which stocks moved together. It describes the past only and doesn't suggest what to buy." />

      <div className="grid grid-cols-1 xl:grid-cols-[430px_minmax(0,1fr)] gap-5">
        <div className="panel p-4 space-y-3 h-fit">
          <div className="grid grid-cols-2 gap-2">
            <label className="text-xs"><span className="text-muted-foreground">Budget ($)</span>
              <input type="number" value={budget} onChange={(e) => setBudget(+e.target.value)} className="mt-1 w-full rounded-lg bg-background/60 border border-border/70 px-2 py-1.5 text-sm font-mono" /></label>
            <label className="text-xs"><span className="text-muted-foreground">History (years)</span>
              <input type="number" min={1} max={10} value={years} onChange={(e) => setYears(Math.max(1, Math.min(10, +e.target.value)))} className="mt-1 w-full rounded-lg bg-background/60 border border-border/70 px-2 py-1.5 text-sm font-mono" /></label>
          </div>
          <div className="flex flex-wrap items-center gap-2 text-[11px]">
            {synced
              ? <span className="chip text-success"><Link2 size={12} /> Following watchlist ({wl.symbols.length})</span>
              : <button onClick={() => setSynced(true)} className="chip hover:text-foreground text-muted-foreground"><RefreshCw size={12} /> Reset to watchlist</button>}
          </div>
          <div className="text-[11px] text-muted-foreground grid grid-cols-[70px_60px_1fr_20px] gap-2 px-1"><span>Ticker</span><span>Weight %</span><span>Note</span><span /></div>
          {rows.map((r, i) => (
            <div key={i} className="grid grid-cols-[70px_60px_1fr_20px] gap-2 items-center">
              <input value={r.ticker} onChange={(e) => edit(rows.map((x, j) => (j === i ? { ...x, ticker: e.target.value.toUpperCase() } : x)))}
                className="rounded-lg bg-background/60 border border-border/70 px-2 py-1 text-sm font-mono font-bold" aria-label="Ticker" />
              <input type="number" value={r.weight} onChange={(e) => edit(rows.map((x, j) => (j === i ? { ...x, weight: +e.target.value } : x)))}
                className="rounded-lg bg-background/60 border border-border/70 px-2 py-1 text-sm font-mono" aria-label="Weight" />
              <input value={r.why} onChange={(e) => edit(rows.map((x, j) => (j === i ? { ...x, why: e.target.value } : x)))}
                className="rounded-lg bg-background/60 border border-border/70 px-2 py-1 text-xs" aria-label="Rationale" />
              <button onClick={() => edit(rows.filter((_, j) => j !== i))} className="text-muted-foreground hover:text-destructive" aria-label="Remove"><Trash2 size={14} /></button>
            </div>
          ))}
          <div className="flex justify-between items-center">
            <button onClick={() => edit([...rows, { ticker: '', weight: 0, why: '' }])} className="text-xs text-primary flex items-center gap-1" disabled={rows.length >= 25}><Plus size={13} /> Add holding</button>
            <span className={`text-xs font-mono ${Math.abs(total - 100) > 0.01 ? 'text-warning' : 'text-muted-foreground'}`}>total {total}%{Math.abs(total - 100) > 0.01 ? ' (rescaled to 100%)' : ''}</span>
          </div>
          <button onClick={run} disabled={loading || rows.filter((r) => r.ticker.trim()).length < 2} className="w-full rounded-xl bg-primary text-primary-foreground font-semibold py-2.5 flex items-center justify-center gap-2 disabled:opacity-60"><Play size={15} /> Analyse portfolio</button>
        </div>

        <div className="space-y-5">
          {loading && <Loading text="Downloading daily prices and building the covariance matrix…" />}
          {error && <ErrorBox message={error} />}
          {!res && !loading && !error && <div className="panel p-8 text-sm text-muted-foreground flex gap-2"><Info size={16} /> {rows.length < 2 ? 'Add at least two tickers to your watchlist (or below) to build a portfolio.' : 'Your watchlist, equally weighted. Adjust weights if you like, then press Analyse.'}</div>}
          {res && !loading && (
            <>
              {res.missing?.length > 0 && <ErrorBox message={`No price history for: ${res.missing.join(', ')} — left out of the analysis.`} />}
              <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
                <Stat label="Average yearly price change" value={signedPct(res.portfolio.expected_return)} hint="over the past window, not a forecast" />
                <Stat label={<Def k="volatility">Price swings (volatility)</Def>} value={pct(res.portfolio.volatility)} hint="per year" />
                <Stat label={<Def k="sharpe">Change per unit of swing (Sharpe)</Def>} value={num(res.portfolio.sharpe)} hint={<>compared with the <Def k="treasury">10-year Treasury</Def> rate of {pct(res.risk_free, 2)}</>} />
                <Stat label="Diversification ratio" value={num(res.diversification_ratio)} hint=">1 = holdings offset each other" />
                <Stat label="Window" value={`${res.observations} days`} hint={`${res.start} → ${res.end}`} />
              </div>

              <div className="grid grid-cols-1 2xl:grid-cols-2 gap-5">
                <div className="panel p-4">
                  <div className="font-semibold text-sm mb-2">Allocation of {money(res.budget)}</div>
                  <div className="h-[230px]">
                    <ResponsiveContainer width="100%" height="100%">
                      <PieChart>
                        <Pie data={res.holdings} dataKey="allocation" nameKey="ticker" innerRadius={55} outerRadius={90} paddingAngle={2}>
                          {res.holdings.map((_: any, i: number) => <Cell key={i} fill={COLORS[i % COLORS.length]} />)}
                        </Pie>
                        <Tooltip contentStyle={{ background: 'hsl(var(--card))', border: '1px solid hsl(var(--border))', borderRadius: 12, fontSize: 12 }} formatter={(v: number) => money(v)} />
                      </PieChart>
                    </ResponsiveContainer>
                  </div>
                </div>
                <div className="panel p-4">
                  <div className="font-semibold text-sm mb-2">How much each stock swung (across) vs how much it changed per year (up), past window</div>
                  <div className="h-[230px]">
                    <ResponsiveContainer width="100%" height="100%">
                      <ScatterChart margin={{ top: 10, right: 20, bottom: 10, left: 0 }}>
                        <CartesianGrid stroke="hsl(var(--border))" strokeDasharray="3 6" />
                        <XAxis type="number" dataKey="x" name="Volatility" unit="%" tick={{ fill: 'hsl(var(--muted-foreground))', fontSize: 11 }} />
                        <YAxis type="number" dataKey="y" name="Return" unit="%" tick={{ fill: 'hsl(var(--muted-foreground))', fontSize: 11 }} width={44} />
                        <Tooltip contentStyle={{ background: 'hsl(var(--card))', border: '1px solid hsl(var(--border))', borderRadius: 12, fontSize: 12 }} formatter={(v: number) => `${v.toFixed(1)}%`} />
                        <Scatter data={scatter} fill="hsl(190 92% 50%)"><LabelList dataKey="name" position="top" fill="hsl(var(--muted-foreground))" fontSize={10} /></Scatter>
                        <Scatter data={portPoints} fill="hsl(38 96% 58%)" shape="diamond"><LabelList dataKey="name" position="right" fill="hsl(38 96% 58%)" fontSize={10} /></Scatter>
                      </ScatterChart>
                    </ResponsiveContainer>
                  </div>
                </div>
              </div>

              <div className="panel p-4 overflow-x-auto">
                <div className="font-semibold text-sm mb-2">Each holding — what it is, how it moved and how much it swung</div>
                <table className="w-full text-xs">
                  <thead><tr className="text-muted-foreground"><th className="text-left font-medium py-1">Ticker</th><th className="text-left font-medium">Sector</th><th className="text-right font-medium">Weight</th><th className="text-right font-medium">Amount</th><th className="text-right font-medium">Shares</th><th className="text-right font-medium">Return</th><th className="text-right font-medium">Volatility</th><th className="text-right font-medium" title="Share of total portfolio risk this holding is responsible for">Risk share</th><th className="text-left font-medium pl-3">Rationale</th></tr></thead>
                  <tbody>
                    {res.holdings.map((h: any, i: number) => (
                      <tr key={h.ticker} className="border-t border-border/50">
                        <td className="py-1.5 font-mono font-bold"><span className="inline-block w-2 h-2 rounded-full mr-1.5" style={{ background: COLORS[i % COLORS.length] }} />{h.ticker}</td>
                        <td className="text-muted-foreground">{res.sectors?.[h.ticker] || 'ETF / other'}</td>
                        <td className="text-right font-mono">{pct(h.weight)}</td><td className="text-right font-mono">{money(h.allocation)}</td>
                        <td className="text-right font-mono" title={`at ${usd(h.last_price)}`}>{h.shares}</td>
                        <td className="text-right font-mono">{signedPct(h.annual_return)}</td><td className="text-right font-mono">{pct(h.annual_volatility)}</td>
                        <td className="text-right font-mono">{pct(h.risk_contribution)}</td>
                        <td className="pl-3 text-muted-foreground">{why[h.ticker] || ''}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              <div className="grid grid-cols-1 2xl:grid-cols-2 gap-5">
                <div className="panel p-4 overflow-x-auto">
                  <div className="font-semibold text-sm mb-2">Which stocks moved together (correlation of daily price changes)</div>
                  <table className="text-[11px] font-mono">
                    <thead><tr><th />{res.correlation.tickers.map((t: string) => <th key={t} className="px-1.5 font-semibold">{t}</th>)}</tr></thead>
                    <tbody>
                      {res.correlation.matrix.map((row: number[], i: number) => (
                        <tr key={i}>
                          <td className="pr-2 font-semibold">{res.correlation.tickers[i]}</td>
                          {row.map((v, j) => (
                            <td key={j} className="px-1.5 py-1 text-center rounded" style={{ background: v >= 0 ? `hsl(350 89% 62% / ${Math.abs(v) * 0.45})` : `hsl(152 70% 46% / ${Math.abs(v) * 0.45})` }}>{v.toFixed(2)}</td>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                  <p className="text-[11px] text-muted-foreground mt-2"><Def k="correlation">Correlation</Def>: how often two stocks moved in the same direction on the same day. 1 = always together, 0 = no link, below 0 = usually opposite. It describes the past window only.</p>
                </div>
              </div>
              <p className="text-[11px] text-muted-foreground">{res.method}</p>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
