/* eslint-disable @typescript-eslint/no-explicit-any */
import { Fragment, useEffect, useState } from 'react';
import { ResponsiveContainer, BarChart, Bar, XAxis, YAxis, Tooltip, CartesianGrid, ComposedChart, Line, Area } from 'recharts';
import { FileBarChart, Users, Coins, ShieldCheck, ShieldAlert, AlertTriangle, ExternalLink, Info, CheckCircle2, XCircle } from 'lucide-react';
import { api } from '@/lib/api';
import { pct, signedPct, mult, money, usd, num, byUnit, errMsg, isNum } from '@/lib/format';
import { useWatchlistTicker, PageHeader, Stat, Loading, ErrorBox, Sources, Tabs } from '@/components/ResearchBits';
import WatchlistTabs from '@/components/WatchlistTabs';
import InvestmentView from '@/components/InvestmentView';
import PlainText, { Def, AutoTerm } from '@/components/PlainText';

type Tab = 'overview' | 'invest' | 'financials' | 'peers' | 'dividends' | 'history';
const TABS: Array<{ key: Tab; label: string }> = [
  { key: 'overview', label: 'Summary' },
  { key: 'invest', label: 'Investment view (buy / hold / sell)' },
  { key: 'financials', label: 'All reported numbers' },
  { key: 'peers', label: 'vs similar companies' },
  { key: 'dividends', label: 'Dividends' },
  { key: 'history', label: 'Share price' },
];

const ROWS: Array<[string, string, 'money' | 'pershare' | 'count']> = [
  ['revenue', 'Revenue', 'money'], ['cost_of_revenue', 'Cost of revenue', 'money'], ['gross_profit', 'Gross profit', 'money'],
  ['operating_income', 'Operating income', 'money'], ['net_income', 'Net income', 'money'], ['eps_diluted', 'Diluted EPS', 'pershare'],
  ['dps', 'Dividends per share', 'pershare'], ['total_assets', 'Total assets', 'money'], ['current_assets', 'Current assets', 'money'],
  ['current_liabilities', 'Current liabilities', 'money'], ['cash', 'Cash & equivalents', 'money'], ['total_debt', 'Total debt', 'money'],
  ['equity', "Shareholders' equity", 'money'], ['operating_cash_flow', 'Operating cash flow', 'money'], ['capex', 'Capital expenditure', 'money'],
  ['free_cash_flow', 'Free cash flow', 'money'], ['dividends_paid', 'Dividends paid', 'money'], ['diluted_shares', 'Diluted shares', 'count'],
];

const fmtItem = (v: number | null | undefined, kind: string, cur: string) =>
  !isNum(v) ? '—' : kind === 'pershare' ? `${v.toFixed(2)}` : kind === 'count' ? `${(v / 1e9).toFixed(3)}B` : cur === 'USD' ? money(v) : `${(v / 1e9).toFixed(2)}B ${cur}`;

/** Badge showing where one figure came from. */
const Prov = ({ p }: { p?: any }) => {
  if (!p) return null;
  const sec = p.source === 'sec' || p.source === 'sec_calc';
  const off = isNum(p.yahoo_diff) && p.yahoo_diff > 0.02;
  const failed = sec && p.check_failed;
  const title = sec
    ? `${failed ? `FAILED CHECK: ${p.check_failed}. Treat this figure with caution. ` : ''}${p.source === 'sec_calc' ? `Calculated from SEC figures: ${p.formula}. ` : ''}${p.form} filed ${p.filed}${p.concept ? ` · ${p.concept}` : ''}${isNum(p.yahoo_diff) ? ` · Yahoo differs by ${(p.yahoo_diff * 100).toFixed(1)}%` : ''}`
    : p.note;
  const cls = failed ? 'text-destructive' : !sec ? 'text-warning' : off ? 'text-info' : 'text-success';
  const body = <span className={`inline-flex ${cls}`} title={title}>{failed ? <ShieldAlert size={11} /> : sec ? <ShieldCheck size={11} /> : <AlertTriangle size={11} />}</span>;
  return p.url ? <a href={p.url} target="_blank" rel="noreferrer" className="ml-1 align-middle">{body}</a> : <span className="ml-1 align-middle">{body}</span>;
};

export default function CompanyReport() {
  const { ticker, setTicker, wl } = useWatchlistTicker();
  const [tab, setTab] = useState<Tab>('overview');
  const [peers, setPeers] = useState('');
  const [peerDraft, setPeerDraft] = useState('');
  const [data, setData] = useState<any>(null);
  const [hist, setHist] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    if (!ticker) return;
    let alive = true;
    setLoading(true); setError(''); setData(null); setHist(null);
    api.getCompanyReport(ticker, peers || undefined)
      .then((r) => { if (alive) { setData(r.data); setPeerDraft(r.data.peers.rows.map((p: any) => p.ticker).join(', ')); } })
      .catch((e) => alive && setError(errMsg(e)))
      .finally(() => alive && setLoading(false));
    api.getPriceHistory(ticker).then((r) => alive && setHist(r.data.metrics)).catch(() => {});
    return () => { alive = false; };
  }, [ticker, peers]);

  return (
    <div className="space-y-5">
      <PageHeader icon={FileBarChart} title="Company Report"
        subtitle="What each company told the SEC (the US market regulator) in its official reports, explained in plain words, compared with similar companies and the overall market. The Investment view tab adds a fair-value estimate and a buy / hold / sell rating from a fixed formula, with every input shown." />
      <WatchlistTabs items={wl.items} loaded={wl.loaded} value={ticker} onChange={(t) => { setPeers(''); setTicker(t); }} onAdd={wl.add} />
      <WatchlistOverview symbols={wl.symbols} selected={ticker} onPick={(t) => { setPeers(''); setTicker(t); }} />

      {loading && <Loading text="Reading the annual reports from SEC EDGAR…" />}
      {error && <ErrorBox message={error} />}

      {data && (
        <>
          <div className="panel p-5 flex flex-wrap items-center justify-between gap-4">
            <div>
              <div className="text-xs text-muted-foreground">{[data.profile.sector, data.profile.industry, data.profile.country].filter(Boolean).join(' · ')}</div>
              <div className="flex items-baseline gap-3 mt-0.5">
                <span className="text-2xl font-bold">{data.profile.name}</span>
                <span className="font-mono text-muted-foreground">{data.profile.ticker}</span>
              </div>
              <div className="text-xs text-muted-foreground mt-1">Latest <Def k="10k">annual report</Def>: <Def k="fiscal_year">fiscal year</Def> ended {data.years[0].fiscal_year_end} · figures in {data.profile.currency}</div>
            </div>
            <div className="flex flex-wrap gap-3">
              <Stat label="Price" value={usd(data.market.price)} hint={`${data.market.source}`} />
              <Stat label="Figures from SEC filings" value={`${data.coverage.from_sec} / ${data.coverage.total}`}
                hint="the rest are from Yahoo or failed a check, and are marked" tone={data.coverage.from_sec === data.coverage.total ? 'text-success' : 'text-warning'} />
              {isNum(data.coverage.checks_run) && (
                <Stat label={<Def k="accounting_check">Accounting checks passed</Def>} value={`${data.coverage.checks_run - data.coverage.checks_failed} / ${data.coverage.checks_run}`}
                  hint="see All reported numbers" tone={data.coverage.checks_failed ? 'text-destructive' : 'text-success'} />
              )}
            </div>
          </div>

          <div className="flex flex-wrap gap-4 text-[11px] text-muted-foreground items-center">
            <span className="flex items-center gap-1"><ShieldCheck size={12} className="text-success" /> as reported to the SEC (click for the filing)</span>
            <span className="flex items-center gap-1"><ShieldCheck size={12} className="text-info" /> SEC figure; Yahoo shows a different number</span>
            <span className="flex items-center gap-1"><AlertTriangle size={12} className="text-warning" /> not in SEC data · from Yahoo, not verified</span>
            <span className="flex items-center gap-1"><ShieldAlert size={12} className="text-destructive" /> SEC figure that failed an accounting check</span>
          </div>

          <Tabs tabs={TABS} value={tab} onChange={(t) => setTab(t as Tab)} />
          {tab === 'overview' && <Overview d={data} />}
          {tab === 'invest' && <InvestmentView ticker={data.profile.ticker} />}
          {tab === 'financials' && <Financials d={data} />}
          {tab === 'peers' && <Peers d={data} draft={peerDraft} setDraft={setPeerDraft} apply={() => setPeers(peerDraft.replace(/\s+/g, ''))} />}
          {tab === 'dividends' && <Dividends d={data} />}
          {tab === 'history' && <PriceCheck ticker={data.profile.ticker} />}
          {tab === 'history' && (hist ? <History h={hist} /> : <Loading text="Loading 3 years of daily prices…" />)}
          <Sources items={data.sources} />
          <p className="text-[11px] text-muted-foreground flex gap-1.5"><Info size={13} className="shrink-0 mt-0.5" />{data.note}</p>
        </>
      )}
    </div>
  );
}

// ---------------------------------------------------------------- watchlist overview
function WatchlistOverview({ symbols, selected, onPick }: { symbols: string[]; selected: string; onPick: (t: string) => void }) {
  const [rows, setRows] = useState<any[] | null>(null);
  const [open, setOpen] = useState(true);
  const [err, setErr] = useState('');
  const key = symbols.join(',');
  useEffect(() => {
    if (!key) { setRows([]); return; }
    let alive = true;
    setErr(''); setRows(null);
    api.getWatchlistSummary().then((r) => alive && setRows(r.data.rows)).catch((e) => alive && setErr(errMsg(e)));
    return () => { alive = false; };
  }, [key]);
  if (!symbols.length) return null;
  return (
    <div className="panel p-4">
      <button onClick={() => setOpen(!open)} className="w-full flex items-center justify-between text-left">
        <span className="font-semibold text-sm">Watchlist overview <span className="text-muted-foreground font-normal">· latest reported year · click a row to open it</span></span>
        <span className="text-xs text-muted-foreground">{open ? 'Hide' : 'Show'}</span>
      </button>
      {open && (
        <div className="overflow-x-auto mt-3 max-h-[360px] overflow-y-auto scroll-panel">
          {err && <div className="text-xs text-destructive">{err}</div>}
          {!rows && !err && <div className="text-xs text-muted-foreground py-4">Reading each company's SEC data — the first load can take up to a minute.</div>}
          {rows && (
            <table className="w-full text-xs">
              <thead className="sticky top-0 bg-card">
                <tr className="text-muted-foreground">
                  {['Company', 'FY end', 'Price', 'Revenue', 'Net income', 'Net margin', 'ROE', 'Debt/eq', 'P/E', 'Div yield', 'From SEC'].map((h, i) => (
                    <th key={h} className={`font-medium py-1.5 ${i < 2 ? 'text-left' : 'text-right'}`}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.ticker} onClick={() => onPick(r.ticker)} className={`border-t border-border/50 cursor-pointer hover:bg-primary/5 ${r.ticker === selected ? 'bg-primary/10' : ''}`}>
                    <td className="py-1.5"><span className="font-mono font-bold">{r.ticker}</span> <span className="text-muted-foreground">{r.name}</span></td>
                    {r.error ? <td colSpan={10} className="text-destructive">{r.error}</td> : (
                      <>
                        <td className="font-mono">{r.fiscal_year_end}</td>
                        <td className="text-right font-mono">{usd(r.price)}</td>
                        <td className="text-right font-mono">{fmtItem(r.revenue, 'money', r.currency)}</td>
                        <td className="text-right font-mono">{fmtItem(r.net_income, 'money', r.currency)}</td>
                        <td className="text-right font-mono">{pct(r.net_margin)}</td>
                        <td className="text-right font-mono">{pct(r.roe)}</td>
                        <td className="text-right font-mono">{mult(r.debt_to_equity)}</td>
                        <td className="text-right font-mono">{r.currency === 'USD' ? mult(r.pe, 1) : '—'}</td>
                        <td className="text-right font-mono">{r.currency === 'USD' ? pct(r.dividend_yield, 2) : '—'}</td>
                        <td className="text-right font-mono">{r.sec_coverage ? `${r.sec_coverage.from_sec}/${r.sec_coverage.total}` : '—'}</td>
                      </>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------- key facts
function Overview({ d }: { d: any }) {
  const y = d.years[0], it = y.items, r = y.ratios, pv = y.provenance, g = d.growth, cur = d.profile.currency;
  const fact = (label: string, value: string, k?: string, gk?: string) => (
    <div className="rounded-xl border border-border/70 bg-background/40 px-3 py-2.5">
      <div className="text-[10px] uppercase tracking-wider text-muted-foreground">{gk ? <Def k={gk}>{label}</Def> : label}</div>
      <div className="font-mono font-bold text-lg mt-0.5">{value}{k && <Prov p={pv[k]} />}</div>
    </div>
  );
  return (
    <div className="space-y-5">
      {d.plain && (
        <div className="panel p-4 text-[13px] space-y-2">
          <div className="text-xs font-semibold text-muted-foreground">In plain words</div>
          <PlainText text={[d.plain.lead, d.plain.points.map((x: string) => `- ${x}`).join('\n'), d.plain.means].filter(Boolean).join('\n\n')} />
        </div>
      )}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        {fact(`Revenue, fiscal ${y.fiscal_year_end.slice(0, 4)}`, fmtItem(it.revenue, 'money', cur), 'revenue', 'revenue')}
        {fact('Net income (profit)', fmtItem(it.net_income, 'money', cur), 'net_income', 'net_income')}
        {fact('Free cash flow', fmtItem(it.free_cash_flow, 'money', cur), 'free_cash_flow', 'free_cash_flow')}
        {fact('Profit per share (EPS)', fmtItem(it.eps_diluted, 'pershare', cur), 'eps_diluted', 'eps')}
        {fact('Net margin', pct(r.net_margin), undefined, 'net_margin')}
        {fact('Return on equity', pct(r.roe), undefined, 'roe')}
        {fact('Debt ÷ equity', mult(r.debt_to_equity), undefined, 'debt_to_equity')}
        {fact('Current ratio', mult(r.current_ratio), undefined, 'current_ratio')}
      </div>
      {g.years && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <Stat label={<Def k="cagr">{`Revenue growth per year (${g.years} yrs)`}</Def>} value={signedPct(g.revenue)} />
          <Stat label="Net income growth per year" value={signedPct(g.net_income)} />
          <Stat label="Profit-per-share growth per year" value={signedPct(g.eps_diluted)} />
          <Stat label="Free cash flow growth per year" value={signedPct(g.free_cash_flow)} />
        </div>
      )}
      {d.profile.summary && (
        <div className="panel p-4">
          <div className="text-xs font-semibold mb-1">Business description <span className="font-normal text-muted-foreground">(company profile via Yahoo Finance)</span></div>
          <p className="text-sm text-muted-foreground leading-relaxed">{d.profile.summary}</p>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------- statements
function Financials({ d }: { d: any }) {
  const years = d.years, cur = d.profile.currency;
  const groups: string[] = Array.from(new Set(d.ratio_definitions.map((r: any) => r.group)));
  const chart = [...years].reverse().map((y: any) => ({ year: y.fiscal_year_end.slice(0, 4), revenue: (y.items.revenue ?? 0) / 1e9, net: (y.items.net_income ?? 0) / 1e9, fcf: (y.items.free_cash_flow ?? 0) / 1e9 }));
  return (
    <div className="space-y-5">
      <div className="panel p-4">
        <div className="font-semibold text-sm mb-2">Revenue, net income and free cash flow (billions {cur})</div>
        <div className="h-[230px]">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={chart}>
              <CartesianGrid stroke="hsl(var(--border))" strokeDasharray="3 6" vertical={false} />
              <XAxis dataKey="year" tick={{ fill: 'hsl(var(--muted-foreground))', fontSize: 11 }} axisLine={false} tickLine={false} />
              <YAxis tick={{ fill: 'hsl(var(--muted-foreground))', fontSize: 11 }} axisLine={false} tickLine={false} width={44} />
              <Tooltip contentStyle={{ background: 'hsl(var(--card))', border: '1px solid hsl(var(--border))', borderRadius: 12, fontSize: 12 }} formatter={(v: number) => `${v.toFixed(2)}B ${cur}`} />
              <Bar dataKey="revenue" name="Revenue" fill="hsl(248 92% 68%)" radius={[4, 4, 0, 0]} />
              <Bar dataKey="net" name="Net income" fill="hsl(152 70% 46%)" radius={[4, 4, 0, 0]} />
              <Bar dataKey="fcf" name="Free cash flow" fill="hsl(190 92% 50%)" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>
      <div className="panel p-4 overflow-x-auto">
        <div className="font-semibold text-sm mb-3">Financial statements (annual, as reported)</div>
        <table className="w-full text-xs">
          <thead><tr className="text-muted-foreground"><th className="text-left font-medium py-1.5">Line item</th>{years.map((y: any) => <th key={y.fiscal_year_end} className="text-right font-medium font-mono">FY{y.fiscal_year_end.slice(0, 4)}</th>)}</tr></thead>
          <tbody>
            {ROWS.map(([k, label, kind]) => (
              <tr key={k} className="border-t border-border/50">
                <td className="py-1.5"><AutoTerm text={label} /></td>
                {years.map((y: any) => <td key={y.fiscal_year_end} className="text-right font-mono whitespace-nowrap">{fmtItem(y.items[k], kind, cur)}{y.items[k] != null && <Prov p={y.provenance[k]} />}</td>)}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <Checks years={years} cur={cur} />
      <div className="panel p-4 overflow-x-auto">
        <div className="font-semibold text-sm mb-1">Ratios</div>
        <p className="text-[11px] text-muted-foreground mb-3">Standard formulas on the figures above; hover a ratio to see its formula. P/E, P/B and dividend yield use today's price, so they appear for the latest year only.</p>
        <table className="w-full text-xs">
          <thead><tr className="text-muted-foreground"><th className="text-left font-medium py-1.5">Ratio</th>{years.map((y: any) => <th key={y.fiscal_year_end} className="text-right font-medium font-mono">FY{y.fiscal_year_end.slice(0, 4)}</th>)}<th className="text-right font-medium">Peer median</th></tr></thead>
          <tbody>
            {groups.map((g) => (
              <Fragment key={g}>
                <tr><td colSpan={years.length + 2} className="pt-3 pb-1 text-[10px] uppercase tracking-wider text-primary">{g}</td></tr>
                {d.ratio_definitions.filter((r: any) => r.group === g).map((r: any) => (
                  <tr key={r.key} className="border-t border-border/50">
                    <td className="py-1.5"><AutoTerm text={r.label} extra={r.formula} /></td>
                    {years.map((y: any) => <td key={y.fiscal_year_end} className="text-right font-mono">{byUnit(y.ratios[r.key], r.unit)}</td>)}
                    <td className="text-right font-mono text-muted-foreground">{byUnit(d.peers.median[r.key], r.unit)}</td>
                  </tr>
                ))}
              </Fragment>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------- accounting checks
function Checks({ years, cur }: { years: any[]; cur: string }) {
  const rows = years.flatMap((y: any) => (y.checks || []).map((c: any) => ({ ...c, year: y.fiscal_year_end.slice(0, 4) })));
  if (!rows.length) return null;
  const failed = rows.filter((c) => !c.passed);
  const show = failed.length ? [...failed, ...rows.filter((c) => c.passed)] : rows;
  const fmt = (v: number) => (Math.abs(v) < 1000 ? v.toFixed(2) : fmtItem(v, 'money', cur));
  return (
    <div className="panel p-4 overflow-x-auto">
      <div className="font-semibold text-sm mb-1">Accounting checks</div>
      <p className="text-[11px] text-muted-foreground mb-3">
        Identities every annual report must satisfy, run on the SEC figures. A failure usually means a figure was tagged differently or restated; affected figures get a red badge.
      </p>
      <table className="w-full text-xs">
        <thead><tr className="text-muted-foreground"><th className="text-left font-medium py-1.5">Check</th><th className="text-left font-medium">FY</th><th className="text-right font-medium">Reported</th><th className="text-right font-medium">Expected</th><th className="text-right font-medium">Difference</th><th className="text-right font-medium">Result</th></tr></thead>
        <tbody>
          {show.map((c, i) => (
            <tr key={i} className="border-t border-border/50">
              <td className="py-1.5">{c.check}</td>
              <td className="font-mono">{c.year}</td>
              <td className="text-right font-mono">{fmt(c.reported)}</td>
              <td className="text-right font-mono">{fmt(c.expected)}</td>
              <td className="text-right font-mono">{(c.difference * 100).toFixed(2)}% <span className="text-muted-foreground">(≤ {(c.tolerance * 100).toFixed(1)}%)</span></td>
              <td className="text-right">{c.passed
                ? <span className="inline-flex items-center gap-1 text-success"><CheckCircle2 size={12} /> pass</span>
                : <span className="inline-flex items-center gap-1 text-destructive font-semibold"><XCircle size={12} /> fail</span>}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ---------------------------------------------------------------- peers
function Peers({ d, draft, setDraft, apply }: { d: any; draft: string; setDraft: (s: string) => void; apply: () => void }) {
  const keys = ['gross_margin', 'operating_margin', 'net_margin', 'roe', 'current_ratio', 'debt_to_equity', 'interest_coverage', 'pe', 'dividend_yield', 'payout_ratio'];
  const defs = Object.fromEntries(d.ratio_definitions.map((r: any) => [r.key, r]));
  const rows = [{ ticker: d.profile.ticker, name: d.profile.name, ratios: d.years[0].ratios, revenue: d.years[0].items.revenue, currency: d.profile.currency, fiscal_year_end: d.years[0].fiscal_year_end }, ...d.peers.rows];
  return (
    <div className="space-y-5">
      <div className="panel p-4 flex flex-wrap items-center gap-3">
        <Users size={16} className="text-primary" />
        <div className="text-sm">Compare with <span className="text-muted-foreground">({d.peers.basis})</span></div>
        <form onSubmit={(e) => { e.preventDefault(); apply(); }} className="flex gap-2 ml-auto">
          <input value={draft} onChange={(e) => setDraft(e.target.value.toUpperCase())} placeholder="e.g. PEP, KDP" aria-label="Peer tickers"
            className="rounded-lg bg-background/60 border border-border/70 px-3 py-1.5 text-xs font-mono w-56" />
          <button className="rounded-lg bg-primary text-primary-foreground text-xs font-semibold px-3">Compare</button>
        </form>
      </div>
      <div className="panel p-4 overflow-x-auto">
        <table className="w-full text-xs">
          <thead><tr className="text-muted-foreground"><th className="text-left font-medium py-1.5">Company</th><th className="text-left font-medium">FY end</th><th className="text-right font-medium">Revenue</th>
            {keys.map((k) => <th key={k} className="text-right font-medium" title={defs[k]?.formula}>{defs[k]?.label}</th>)}</tr></thead>
          <tbody>
            {rows.map((p: any, i: number) => (
              <tr key={p.ticker} className={`border-t border-border/50 ${i === 0 ? 'bg-primary/5' : ''}`}>
                <td className="py-1.5"><span className="font-mono font-bold">{p.ticker}</span> <span className="text-muted-foreground">{p.name}</span>{p.error && <span className="text-destructive"> · {p.error}</span>}</td>
                <td className="font-mono">{p.fiscal_year_end || '—'}</td>
                <td className="text-right font-mono">{fmtItem(p.revenue, 'money', p.currency || 'USD')}</td>
                {keys.map((k) => <td key={k} className="text-right font-mono">{byUnit(p.ratios?.[k], defs[k]?.unit)}</td>)}
              </tr>
            ))}
            {d.peers.rows.length > 0 && (
              <tr className="border-t-2 border-border"><td className="py-1.5 font-semibold">Peer median</td><td /><td />
                {keys.map((k) => <td key={k} className="text-right font-mono font-semibold">{byUnit(d.peers.median[k], defs[k]?.unit)}</td>)}</tr>
            )}
          </tbody>
        </table>
        <p className="text-[11px] text-muted-foreground mt-3">Each company's latest annual report; fiscal years can end in different months. Companies reporting in another currency (e.g. TWD) are comparable on percentages and ratios, not on amounts.</p>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------- dividends
function Dividends({ d }: { d: any }) {
  const div = d.dividends, y = d.years[0];
  if (!div.pays_dividend) return <div className="panel p-6 text-sm text-muted-foreground">No dividends per share are reported in {d.profile.name}'s SEC data for these years.</div>;
  return (
    <div className="space-y-5">
      <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
        <Stat label={`Dividends per share FY${y.fiscal_year_end.slice(0, 4)}`} value={fmtItem(y.items.dps, 'pershare', d.profile.currency)} hint="declared, as reported" />
        <Stat label="Dividend yield" value={pct(y.ratios.dividend_yield, 2)} hint="dividends per share ÷ today's price" />
        <Stat label="Payout ratio" value={pct(y.ratios.payout_ratio)} hint="dividends paid ÷ net income" />
      </div>
      <div className="panel p-4">
        <div className="font-semibold text-sm mb-2 flex items-center gap-2"><Coins size={15} className="text-primary" /> Dividends per share by fiscal year</div>
        <div className="h-[220px]">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={div.annual}>
              <CartesianGrid stroke="hsl(var(--border))" strokeDasharray="3 6" vertical={false} />
              <XAxis dataKey="year" tick={{ fill: 'hsl(var(--muted-foreground))', fontSize: 11 }} axisLine={false} tickLine={false} />
              <YAxis tick={{ fill: 'hsl(var(--muted-foreground))', fontSize: 11 }} axisLine={false} tickLine={false} width={40} />
              <Tooltip contentStyle={{ background: 'hsl(var(--card))', border: '1px solid hsl(var(--border))', borderRadius: 12, fontSize: 12 }} formatter={(v: number) => v.toFixed(3)} />
              <Bar dataKey="dps" name="Dividends per share" fill="hsl(152 70% 46%)" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
        <p className="text-[11px] text-muted-foreground mt-2">Source: {div.source}.</p>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------- reasons to buy / sell, tested
function PriceCheck({ ticker }: { ticker: string }) {
  const [since, setSince] = useState('');
  const [d, setD] = useState<any>(null);
  const [err, setErr] = useState('');
  useEffect(() => {
    let alive = true;
    setErr('');
    api.getPriceCheck(ticker, since || undefined).then((r) => alive && setD(r.data)).catch((e) => alive && setErr(errMsg(e)));
    return () => { alive = false; };
  }, [ticker, since]);
  if (err) return <ErrorBox message={err} />;
  if (!d) return <Loading text="Comparing with the S&P 500 and the sector…" />;
  const cols = [ticker, ...d.benchmarks];
  return (
    <div className="panel p-4 space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <div className="font-semibold text-sm">Check a reason people give for buying or selling</div>
          <p className="text-[11px] text-muted-foreground max-w-2xl">“It's too up-and-down” and “it keeps going down” are the two most common. Here is what the price actually did, compared with the overall market (S&P 500) and similar companies.</p>
        </div>
        <label className="text-xs"><span className="text-muted-foreground">Bought or sold on (optional)</span>
          <input type="date" value={since} onChange={(e) => setSince(e.target.value)} className="mt-1 block rounded-lg bg-background/60 border border-border/70 px-2 py-1 text-xs font-mono" /></label>
      </div>
      {d.story && (
        <div className="rounded-xl bg-primary/5 border border-primary/20 p-3 text-[13px]">
          <PlainText text={[...d.story.lead, ...(d.story.since || [])].join(' ')} />
        </div>
      )}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-3">
        {d.checks.map((c: any) => (
          <div key={c.claim} className="rounded-xl border border-border/70 bg-background/40 p-3">
            <div className="text-xs font-semibold mb-1.5">“{c.claim}”</div>
            <PlainText className="text-[11.5px] text-muted-foreground" text={c.facts.map((f: string) => `- ${f}`).join('\n')} />
          </div>
        ))}
      </div>
      {d.story?.means && <PlainText className="text-[11.5px] text-muted-foreground" text={d.story.means} />}
      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead><tr className="text-muted-foreground"><th className="text-left font-medium py-1.5"><Def k="return">Price change</Def></th>{cols.map((c) => <th key={c} className="text-right font-medium">{c}</th>)}</tr></thead>
          <tbody>
            {d.periods.map((r: any) => (
              <tr key={r.period} className="border-t border-border/50"><td className="py-1.5">{r.period}</td>
                {cols.map((c) => <td key={c} className={`text-right font-mono ${isNum(r[c]) ? (r[c] >= 0 ? 'text-success' : 'text-destructive') : ''}`}>{signedPct(r[c])}</td>)}</tr>
            ))}
            <tr className="border-t border-border/50"><td className="py-1.5"><Def k="volatility">How much the price swings (volatility, past year)</Def></td>{cols.map((c) => <td key={c} className="text-right font-mono">{pct(d.volatility_1y[c])}</td>)}</tr>
          </tbody>
        </table>
        <div className="flex flex-wrap gap-1 mt-3">
          {d.months.map((m: any) => (
            <span key={m.month} title={`${m.month}: ${signedPct(m.return)}`} className={`rounded px-1.5 py-0.5 text-[10px] font-mono ${m.return >= 0 ? 'bg-success/15 text-success' : 'bg-destructive/15 text-destructive'}`}>{m.month.slice(2)} {signedPct(m.return, 0)}</span>
          ))}
        </div>
        <p className="text-[11px] text-muted-foreground mt-2">Each box above is one month: green = the price rose that month, red = it fell. {d.source}. Prices to {d.as_of}.</p>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------- price history
function History({ h }: { h: any }) {
  return (
    <div className="space-y-5">
      <div className="grid grid-cols-2 md:grid-cols-4 xl:grid-cols-7 gap-3">
        <Stat label="Average yearly price change" value={signedPct(h.annual_return)} hint="in the past; not a forecast" />
        <Stat label={<Def k="volatility">Price swings (volatility)</Def>} value={pct(h.annual_volatility)} hint="per year, from daily moves" />
        <Stat label={<Def k="drawdown">Biggest drop from a high</Def>} value={pct(h.max_drawdown)} />
        <Stat label="Moves with the market (beta)" value={num(h.beta)} hint="1 = moves like the S&P 500; 2 = about twice as much" />
        <Stat label="How closely it follows the market" value={num(h.correlation_to_market)} hint="1 = in step; 0 = no link" />
        <Stat label="Biggest one-day fall" value={pct(h.worst_day)} />
        <Stat label="A bad day (1 in 20)" value={pct(-h.var_95_1d_historical, 2)} hint="on 1 trading day in 20 it fell this much or more" />
      </div>
      <div className="panel p-4">
        <div className="font-semibold text-sm mb-2">Share price (line) and how far below its previous high it was (red area) · {h.window?.start} → {h.window?.end}</div>
        <div className="h-[260px]">
          <ResponsiveContainer width="100%" height="100%">
            <ComposedChart data={h.chart}>
              <CartesianGrid stroke="hsl(var(--border))" strokeDasharray="3 6" vertical={false} />
              <XAxis dataKey="date" tick={{ fill: 'hsl(var(--muted-foreground))', fontSize: 11 }} axisLine={false} tickLine={false} minTickGap={50} />
              <YAxis yAxisId="p" orientation="right" tick={{ fill: 'hsl(var(--muted-foreground))', fontSize: 11 }} axisLine={false} tickLine={false} width={44} domain={['auto', 'auto']} />
              <YAxis yAxisId="d" tick={{ fill: 'hsl(var(--muted-foreground))', fontSize: 11 }} axisLine={false} tickLine={false} width={44} tickFormatter={(v) => `${(v * 100).toFixed(0)}%`} />
              <Tooltip contentStyle={{ background: 'hsl(var(--card))', border: '1px solid hsl(var(--border))', borderRadius: 12, fontSize: 12 }} formatter={(v: number, n: string) => (n === 'Fall from peak' ? pct(v) : usd(v))} />
              <Area yAxisId="d" dataKey="drawdown" name="Fall from peak" fill="hsl(350 89% 62% / 0.2)" stroke="hsl(350 89% 62%)" strokeWidth={1} />
              <Line yAxisId="p" dataKey="price" name="Price" stroke="hsl(248 92% 68%)" dot={false} strokeWidth={1.6} />
            </ComposedChart>
          </ResponsiveContainer>
        </div>
        <p className="text-[11px] text-muted-foreground mt-2 flex gap-1.5"><ExternalLink size={12} className="shrink-0 mt-0.5" />{h.source}. Historical statistics describe the past only.</p>
      </div>
    </div>
  );
}
