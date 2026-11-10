/* eslint-disable @typescript-eslint/no-explicit-any */
import { useEffect, useState } from 'react';
import { ExternalLink, Scale, Coins, ShieldAlert, PieChart as PieIcon, Calculator } from 'lucide-react';
import { api } from '@/lib/api';
import { pct, signedPct, usd, num, errMsg, isNum } from '@/lib/format';
import { Loading, ErrorBox, LEVEL_CLS } from '@/components/ResearchBits';
import PlainText, { Def } from '@/components/PlainText';

/**
 * Investment view: the method of the team report on Coca-Cola, applied to the selected company.
 * Valuation → rating → dividends → risk checks → model portfolio. (The report's capital-budgeting part is left out.)
 * Everything here comes from app/internal/valuation.py: a fixed formula, no AI.
 */
const RATING_CLS: Record<string, string> = {
  BUY: 'bg-success/15 text-success border-success/40', HOLD: 'bg-warning/15 text-warning border-warning/40',
  SELL: 'bg-destructive/15 text-destructive border-destructive/40',
};
const bullets = (xs: string[]) => xs.map((x) => `- ${x}`).join('\n');
const shown = (v: number | null | undefined, unit: string) => (!isNum(v) ? '—' : unit === '%' ? pct(v, 2) : unit === 'x' ? num(v) : usd(v));

/** Where today's price sits against the BUY / HOLD / SELL zones. */
function Bands({ v }: { v: any }) {
  const lo = Math.min(v.buy_below, v.price) * 0.94, hi = Math.max(v.sell_above, v.price) * 1.06;
  const x = (p: number) => `${((p - lo) / (hi - lo)) * 100}%`;
  return (
    <div className="mt-3">
      <div className="relative h-7 rounded-lg overflow-hidden border border-border/70 text-[10px] font-semibold">
        <div className="absolute inset-y-0 left-0 bg-success/20 text-success grid place-items-center" style={{ width: x(v.buy_below) }}>BUY</div>
        <div className="absolute inset-y-0 bg-warning/15 text-warning grid place-items-center" style={{ left: x(v.buy_below), width: `calc(${x(v.sell_above)} - ${x(v.buy_below)})` }}>HOLD</div>
        <div className="absolute inset-y-0 right-0 bg-destructive/15 text-destructive grid place-items-center" style={{ left: x(v.sell_above) }}>SELL</div>
        <div className="absolute inset-y-0 w-0.5 bg-foreground" style={{ left: x(v.price) }} title={`Price ${usd(v.price)}`} />
        <div className="absolute inset-y-0 w-px border-l border-dashed border-foreground/50" style={{ left: x(v.fair_value) }} title={`Fair value ${usd(v.fair_value)}`} />
      </div>
      <div className="relative h-4 text-[10px] font-mono text-muted-foreground mt-1">
        <span className="absolute -translate-x-1/2" style={{ left: x(v.buy_below) }}>{usd(v.buy_below)}</span>
        <span className="absolute -translate-x-1/2" style={{ left: x(v.sell_above) }}>{usd(v.sell_above)}</span>
      </div>
      <div className="text-[11px] text-muted-foreground mt-1">Solid line = today's price ({usd(v.price)}) · dashed line = fair value ({usd(v.fair_value)})</div>
    </div>
  );
}

function ModelPortfolio({ ticker }: { ticker: string }) {
  const [p, setP] = useState<any>(null);
  const [err, setErr] = useState('');
  useEffect(() => {
    let alive = true;
    setP(null); setErr('');
    api.getModelPortfolio(ticker).then((r) => alive && setP(r.data)).catch((e) => alive && setErr(errMsg(e)));
    return () => { alive = false; };
  }, [ticker]);
  if (err) return <ErrorBox message={err} />;
  if (!p) return <Loading text="Loading the five index funds…" />;
  const t = p.total;
  return (
    <div className="panel p-4 space-y-3">
      <div className="font-semibold text-sm flex items-center gap-2"><PieIcon size={15} className="text-primary" /> 4 · A diversified portfolio around {ticker}</div>
      <PlainText className="text-[13px]" text={`${p.story.lead.join(' ')}\n\n${bullets(p.story.points)}`} />
      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead><tr className="text-muted-foreground">
            <th className="text-left font-medium py-1.5">Holding</th><th className="text-left font-medium">What it is</th>
            <th className="text-right font-medium">Share</th><th className="text-right font-medium">Amount</th>
            <th className="text-right font-medium"><Def k="beta">Beta</Def></th><th className="text-right font-medium">Yield</th>
            <th className="text-right font-medium"><Def k="expected_return">Expected return</Def></th>
            <th className="text-right font-medium"><Def k="expense_ratio">Yearly fee</Def></th>
            <th className="text-right font-medium"><Def k="stress_test">Bear-market test</Def></th>
          </tr></thead>
          <tbody>
            {p.rows.map((r: any) => (
              <tr key={r.symbol} className="border-t border-border/50">
                <td className="py-1.5 font-mono font-bold">{r.symbol}</td><td className="text-muted-foreground">{r.asset_class}{r.kind !== 'stock' ? ` · ${r.name}` : ''}</td>
                <td className="text-right font-mono">{pct(r.weight, 0)}</td><td className="text-right font-mono">{usd(r.amount, 0)}</td>
                <td className="text-right font-mono">{num(r.beta)}</td><td className="text-right font-mono">{pct(r.yield, 2)}</td>
                <td className="text-right font-mono">{pct(r.expected_return)}</td><td className="text-right font-mono">{isNum(r.expense_ratio) ? pct(r.expense_ratio, 2) : '—'}</td>
                <td className="text-right font-mono">{signedPct(r.stress)}</td>
              </tr>
            ))}
            <tr className="border-t border-border font-semibold">
              <td className="py-1.5">Total</td><td /><td className="text-right font-mono">100%</td><td className="text-right font-mono">{usd(p.budget, 0)}</td>
              <td className="text-right font-mono">{num(t.beta)}</td><td className="text-right font-mono">{pct(t.yield, 2)}</td>
              <td className="text-right font-mono">{pct(t.expected_return)}</td><td className="text-right font-mono">{pct(t.expense_ratio, 2)}</td>
              <td className="text-right font-mono">{signedPct(t.stress)}</td>
            </tr>
          </tbody>
        </table>
      </div>
      <PlainText className="text-[11.5px] text-muted-foreground" text={`${p.story.means}\n\n**Assumptions**\n${bullets(p.assumptions)}`} />
      <p className="text-[11px] text-muted-foreground">{p.source}</p>
    </div>
  );
}

export default function InvestmentView({ ticker }: { ticker: string }) {
  const [v, setV] = useState<any>(null);
  const [err, setErr] = useState('');
  useEffect(() => {
    let alive = true;
    setV(null); setErr('');
    api.getValuation(ticker).then((r) => alive && setV(r.data)).catch((e) => alive && setErr(errMsg(e)));
    return () => { alive = false; };
  }, [ticker]);
  if (err) return <ErrorBox message={err} />;
  if (!v) return <Loading text="Working out the fair value from dividends, past price tags and analyst targets…" />;
  const s = v.story, coe = v.cost_of_equity;
  const ddm = v.methods.find((m: any) => m.key === 'ddm'), pe = v.methods.find((m: any) => m.key === 'pe');
  return (
    <div className="space-y-5">
      {/* 1 · rating */}
      <div className="panel p-5">
        <div className="flex flex-wrap items-start gap-5">
          <div className={`rounded-2xl border px-5 py-3 text-center min-w-[120px] ${v.rating ? RATING_CLS[v.rating] : 'bg-secondary text-muted-foreground border-border'}`}>
            <div className="text-[10px] uppercase tracking-wider opacity-80"><Def k="rating">Formula rating</Def></div>
            <div className="text-3xl font-bold tracking-tight">{v.rating || 'None'}</div>
          </div>
          <div className="flex-1 min-w-[260px] text-[13.5px]">
            <PlainText text={s.lead.join(' ')} />
            {v.rating && <Bands v={v} />}
          </div>
        </div>
        <PlainText className="text-[12px] text-muted-foreground mt-4" text={s.means} />
      </div>

      {/* 2 · valuation */}
      <div className="panel p-4 space-y-3">
        <div className="font-semibold text-sm flex items-center gap-2"><Scale size={15} className="text-primary" /> 1 · What a share is estimated to be worth</div>
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead><tr className="text-muted-foreground"><th className="text-left font-medium py-1.5">Method</th><th className="text-left font-medium">Formula</th><th className="text-right font-medium">Value per share</th><th className="text-right font-medium">vs today's price</th></tr></thead>
            <tbody>
              {v.methods.map((m: any) => (
                <tr key={m.key} className="border-t border-border/50">
                  <td className="py-1.5 font-semibold"><Def k={m.key === 'ddm' ? 'ddm' : m.key === 'pe' ? 'hist_pe' : 'analyst_target'}>{m.name}</Def></td>
                  <td className="text-muted-foreground">{m.available ? m.formula : `Not used: ${m.why}`}</td>
                  <td className="text-right font-mono">{m.available ? usd(m.value) : '—'}</td>
                  <td className="text-right font-mono">{m.available ? signedPct(m.vs_price) : '—'}</td>
                </tr>
              ))}
              <tr className="border-t border-border font-semibold">
                <td className="py-1.5"><Def k="fair_value">Fair value</Def></td><td className="text-muted-foreground font-normal">plain average of the methods used</td>
                <td className="text-right font-mono">{usd(v.fair_value)}</td><td className="text-right font-mono">{isNum(v.gap) ? signedPct(v.gap) : '—'}</td>
              </tr>
            </tbody>
          </table>
        </div>
        <PlainText className="text-[12.5px]" text={bullets([...s.methods, ...s.required_return])} />
      </div>

      {/* what-if + P/E history */}
      <div className="grid grid-cols-1 xl:grid-cols-2 gap-5">
        {ddm?.available && (
          <div className="panel p-4">
            <div className="font-semibold text-sm mb-1 flex items-center gap-2"><Calculator size={15} className="text-primary" /> What if the assumptions are a little different?</div>
            <p className="text-[11px] text-muted-foreground mb-2">Dividend-method value per share. Each row is a different required return; each column a different dividend growth rate. Small changes move the answer a lot, which is why Oracle averages three methods.</p>
            <table className="w-full text-xs">
              <thead><tr className="text-muted-foreground"><th className="text-left font-medium py-1.5">Required return ↓ / growth →</th>
                {ddm.sensitivity[0].values.map((c: any) => <th key={c.g} className="text-right font-medium font-mono">{pct(c.g, 2)}</th>)}</tr></thead>
              <tbody>
                {ddm.sensitivity.map((r: any) => (
                  <tr key={r.ke} className="border-t border-border/50"><td className="py-1.5 font-mono">{pct(r.ke, 2)}</td>
                    {r.values.map((c: any) => {
                      const base = Math.abs(r.ke - ddm.ke) < 1e-9 && Math.abs(c.g - ddm.g) < 1e-9;
                      return <td key={c.g} className={`text-right font-mono ${base ? 'font-bold text-primary' : ''}`}>{isNum(c.value) ? usd(c.value) : '—'}</td>;
                    })}</tr>
                ))}
              </tbody>
            </table>
            <p className="text-[11px] text-muted-foreground mt-2">Highlighted = the case Oracle uses.</p>
          </div>
        )}
        {pe?.rows?.length > 0 && (
          <div className="panel p-4">
            <div className="font-semibold text-sm mb-1">The price tag investors put on profit, year by year</div>
            <p className="text-[11px] text-muted-foreground mb-2"><Def k="pe">P/E</Def> = share price at the fiscal year-end ÷ that year's profit per share.</p>
            <table className="w-full text-xs">
              <thead><tr className="text-muted-foreground"><th className="text-left font-medium py-1.5">Fiscal year</th><th className="text-right font-medium">Year-end price</th><th className="text-right font-medium">Profit per share</th><th className="text-right font-medium">P/E</th></tr></thead>
              <tbody>
                {pe.rows.map((r: any) => (
                  <tr key={r.year} className="border-t border-border/50"><td className="py-1.5 font-mono">{r.year}</td>
                    <td className="text-right font-mono">{usd(r.price)}</td>
                    <td className="text-right font-mono">{usd(r.eps)}{r.url && <a href={r.url} target="_blank" rel="noreferrer" className="ml-1 text-info inline-flex align-middle" aria-label="SEC filing"><ExternalLink size={10} /></a>}</td>
                    <td className={`text-right font-mono ${r.used ? '' : 'text-muted-foreground line-through'}`} title={r.used ? '' : 'Left out of the average: too high to be meaningful'}>{num(r.pe, 1)}</td></tr>
                ))}
                {pe.available && <tr className="border-t border-border font-semibold"><td className="py-1.5" colSpan={3}>Average</td><td className="text-right font-mono">{num(pe.avg_pe, 1)}</td></tr>}
              </tbody>
            </table>
            <p className="text-[11px] text-muted-foreground mt-2">Year-end prices: Yahoo Finance closes (not verified). Profit per share: SEC annual reports.</p>
          </div>
        )}
      </div>

      {/* inputs */}
      <div className="panel p-4">
        <div className="font-semibold text-sm mb-2">Every input, with its source</div>
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <tbody>
              {v.inputs.map((i: any) => (
                <tr key={i.input} className="border-t border-border/50">
                  <td className="py-1.5 font-semibold whitespace-nowrap pr-3">{i.input}</td><td className="font-mono text-right pr-4 whitespace-nowrap">{shown(i.value, i.unit)}</td>
                  <td className="text-muted-foreground">{i.source}{i.url && <a href={i.url} target="_blank" rel="noreferrer" className="ml-1 text-info inline-flex align-middle" aria-label="Open source"><ExternalLink size={11} /></a>}</td>
                </tr>
              ))}
              <tr className="border-t border-border/50"><td className="py-1.5 font-semibold pr-3"><Def k="adj_beta">Adjusted beta</Def></td><td className="font-mono text-right pr-4">{num(coe.beta)}</td><td className="text-muted-foreground">0.67 × raw beta + 0.33 (Blume formula)</td></tr>
              <tr className="border-t border-border/50"><td className="py-1.5 font-semibold pr-3"><Def k="cost_of_equity">Required return</Def></td><td className="font-mono text-right pr-4">{pct(coe.ke, 2)}</td><td className="text-muted-foreground">{coe.formula}</td></tr>
            </tbody>
          </table>
        </div>
        <PlainText className="text-[11.5px] text-muted-foreground mt-3" text={`**Assumptions**\n${bullets(v.assumptions)}`} />
      </div>

      {/* 3 · dividends */}
      <div className="panel p-4 space-y-3">
        <div className="font-semibold text-sm flex items-center gap-2"><Coins size={15} className="text-primary" /> 2 · Dividends</div>
        <PlainText className="text-[12.5px]" text={bullets(s.dividends)} />
        {v.dividends.years?.some((y: any) => isNum(y.dps)) && (
          <table className="w-full text-xs">
            <thead><tr className="text-muted-foreground"><th className="text-left font-medium py-1.5">Fiscal year</th><th className="text-right font-medium">Dividend per share</th><th className="text-right font-medium">Profit per share</th>
              <th className="text-right font-medium"><Def k="payout_ratio">Paid out</Def></th><th className="text-right font-medium">Dividends paid</th><th className="text-right font-medium"><Def k="free_cash_flow">Free cash flow</Def></th></tr></thead>
            <tbody>
              {v.dividends.years.map((y: any) => (
                <tr key={y.year} className="border-t border-border/50"><td className="py-1.5 font-mono">{y.year}</td><td className="text-right font-mono">{usd(y.dps)}</td><td className="text-right font-mono">{usd(y.eps)}</td>
                  <td className="text-right font-mono">{pct(y.payout, 0)}</td><td className="text-right font-mono">{isNum(y.dividends_paid) ? `$${(y.dividends_paid / 1e9).toFixed(1)}B` : '—'}</td>
                  <td className="text-right font-mono">{isNum(y.free_cash_flow) ? `$${(y.free_cash_flow / 1e9).toFixed(1)}B` : '—'}</td></tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* 4 · risk checks */}
      <div className="panel p-4 space-y-3">
        <div className="font-semibold text-sm flex items-center gap-2"><ShieldAlert size={15} className="text-primary" /> 3 · Risk checks</div>
        <p className="text-[11px] text-muted-foreground">Checks Oracle can measure from the data. Each level (Low, Medium, High) follows the rule shown next to it.</p>
        <div className="space-y-2">
          {v.risks.map((r: any, i: number) => (
            <div key={r.risk} className="flex gap-3 items-start rounded-xl border border-border/70 bg-background/40 p-3">
              <span className={`rounded-full px-2 py-0.5 text-[10px] font-semibold shrink-0 ${LEVEL_CLS[r.level] || 'bg-secondary'}`}>{r.level}</span>
              <PlainText className="text-[12px]" text={s.risks[i].replace(`${r.risk} — ${r.level}. `, `**${r.risk}.** `)} />
            </div>
          ))}
        </div>
        <p className="text-[11.5px] text-muted-foreground">{s.risks[s.risks.length - 1]}</p>
      </div>

      <ModelPortfolio ticker={ticker} />
      <p className="text-[11px] text-muted-foreground">{v.note} Price: {v.price_source}, {v.price_as_of}.</p>
    </div>
  );
}
