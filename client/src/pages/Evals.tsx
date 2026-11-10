/* eslint-disable @typescript-eslint/no-explicit-any */
import { useEffect, useState } from 'react';
import { ResponsiveContainer, BarChart, Bar, XAxis, YAxis, Tooltip, CartesianGrid } from 'recharts';
import { FlaskConical, Play, CheckCircle2, XCircle, Info } from 'lucide-react';
import { api } from '@/lib/api';
import { pct, errMsg, isNum } from '@/lib/format';
import { PageHeader, Stat, ErrorBox, Loading } from '@/components/ResearchBits';
import { useWatchlist } from '@/hooks/useWatchlist';

const tone = (v?: number | null, good = 0.9, ok = 0.7) => (!isNum(v) ? '' : v >= good ? 'text-success' : v >= ok ? 'text-warning' : 'text-destructive');

export default function Evals() {
  const wl = useWatchlist();
  const [s, setS] = useState<any>(null);
  const [run, setRun] = useState<any>(null);
  const [ticker, setTicker] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const load = () => api.getEvalSummary(7).then((r) => {
    setS(r.data);
    if (r.data.last_run && !run) api.getEvalRun(r.data.last_run.id).then((x) => setRun(x.data)).catch(() => {});
  }).catch((e) => setError(errMsg(e)));
  useEffect(() => { load(); }, []); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { if (!ticker && wl.symbols.length) setTicker(wl.symbols[0]); }, [wl.symbols, ticker]);

  const start = async () => {
    setBusy(true); setError('');
    try { const r = await api.runEvals(ticker, 10); setRun(r.data); load(); } catch (e) { setError(errMsg(e)); }
    setBusy(false);
  };

  const f = s?.relationship_funnel || {};
  const funnel = [
    { k: 'Proposed by AI', v: f.proposed || 0 }, { k: 'Not a listed company', v: f.unlisted || 0 },
    { k: 'Quote not in source', v: f.ungrounded || 0 }, { k: 'Saved (verified)', v: f.saved || 0 },
  ];

  return (
    <div className="space-y-5">
      <PageHeader icon={FlaskConical} title="AI quality (evals)"
        subtitle="How grounded Oracle's AI is, measured on every answer and on a fixed benchmark: how often answers cite sources, how many numbers can't be found in those sources, accuracy on facts with a known answer, and how many AI-proposed relationships pass verification." />
      {error && <ErrorBox message={error} />}
      {!s && !error && <Loading text="Loading metrics…" />}

      {s && (
        <>
          <div className="text-xs text-muted-foreground">Live answers, last {s.window_days} days · model {s.llm_usage?.model} · {s.llm_usage?.total?.used}/{s.llm_usage?.total?.cap} AI requests today</div>
          <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-6 gap-3">
            <Stat label="AI answers logged" value={s.answers} hint={Object.entries(s.by_kind || {}).map(([k, v]) => `${k} ${v}`).join(' · ') || 'none yet'} />
            <Stat label="Answers citing sources" value={pct(s.citation_rate, 0)} tone={tone(s.citation_rate)} hint="at least one [S#] or [F]" />
            <Stat label="Answers with clean numbers" value={pct(s.clean_number_rate, 0)} tone={tone(s.clean_number_rate)} hint="every number found in sources" />
            <Stat label="Answers with no advice" value={pct(s.policy_clean_rate, 0)} tone={tone(s.policy_clean_rate)} hint={`${s.policy_removed_total ?? 0} sentences removed by the facts-only rule`} />
            <Stat label="Retrieved sources used" value={pct(s.source_use_rate, 0)} hint="cited ÷ retrieved" />
            <Stat label="Latency p50 / p95" value={s.latency_ms?.p50 ? `${(s.latency_ms.p50 / 1000).toFixed(1)}s` : '—'} hint={s.latency_ms?.p95 ? `p95 ${(s.latency_ms.p95 / 1000).toFixed(1)}s` : ''} />
          </div>

          {s.relationship_rejected?.length > 0 && (
            <div className="panel p-4">
              <div className="font-semibold text-sm mb-1">Relationship proposals that were rejected</div>
              <p className="text-[11px] text-muted-foreground mb-2">The AI suggested these partners, but they were not saved because the evidence rule failed.</p>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-1.5 text-xs">
                {s.relationship_rejected.map((x: any, i: number) => (
                  <div key={i} className="rounded-lg border border-border/60 bg-background/40 px-2.5 py-1.5 flex justify-between gap-2">
                    <span><b className="font-mono">{x.ticker}</b> → {x.company}</span><span className="text-muted-foreground">{x.reason}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {s.policy_recent?.length > 0 && (
            <div className="panel p-4">
              <div className="font-semibold text-sm mb-1">Removed by the facts-only rule</div>
              <p className="text-[11px] text-muted-foreground mb-2">Sentences the AI wrote that gave a rating, recommendation, price target or prediction. They were cut before you saw the answer.</p>
              <div className="space-y-1.5 text-xs max-h-[220px] overflow-y-auto scroll-panel">
                {s.policy_recent.flatMap((r: any, i: number) => r.removed.map((x: any, j: number) => (
                  <div key={`${i}-${j}`} className="rounded-lg border border-border/60 bg-background/40 px-2.5 py-1.5">
                    <span className="font-mono text-muted-foreground">{r.kind}{r.ticker ? ` · ${r.ticker}` : ''} · {r.at.slice(0, 16)}</span>
                    <span className="ml-2 text-warning">{x.kinds.join(', ')}</span>
                    <div className="mt-0.5 line-through text-muted-foreground">{x.sentence}</div>
                  </div>
                )))}
              </div>
            </div>
          )}

          <div className="grid grid-cols-1 xl:grid-cols-2 gap-5">
            <div className="panel p-4">
              <div className="font-semibold text-sm mb-2">Daily answers — cited and number-clean</div>
              {s.daily.length ? (
                <div className="h-[220px]">
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={s.daily}>
                      <CartesianGrid stroke="hsl(var(--border))" strokeDasharray="3 6" vertical={false} />
                      <XAxis dataKey="day" tick={{ fill: 'hsl(var(--muted-foreground))', fontSize: 11 }} axisLine={false} tickLine={false} />
                      <YAxis tick={{ fill: 'hsl(var(--muted-foreground))', fontSize: 11 }} axisLine={false} tickLine={false} width={30} allowDecimals={false} />
                      <Tooltip contentStyle={{ background: 'hsl(var(--card))', border: '1px solid hsl(var(--border))', borderRadius: 12, fontSize: 12 }} />
                      <Bar dataKey="answers" name="Answers" fill="hsl(var(--muted-foreground) / 0.35)" radius={[3, 3, 0, 0]} />
                      <Bar dataKey="cited" name="Cited" fill="hsl(248 92% 68%)" radius={[3, 3, 0, 0]} />
                      <Bar dataKey="clean" name="Clean numbers" fill="hsl(152 70% 46%)" radius={[3, 3, 0, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              ) : <div className="text-sm text-muted-foreground py-8 text-center">Ask the AI Analyst or run the benchmark to start collecting metrics.</div>}
            </div>
            <div className="panel p-4">
              <div className="font-semibold text-sm mb-2">Relationship verification funnel</div>
              <div className="space-y-2">
                {funnel.map((x) => (
                  <div key={x.k} className="grid grid-cols-[160px_1fr_50px] gap-2 items-center text-xs">
                    <span className="text-muted-foreground">{x.k}</span>
                    <div className="h-2.5 rounded bg-muted overflow-hidden"><div className="h-full bg-primary/70" style={{ width: `${f.proposed ? (x.v / f.proposed) * 100 : 0}%` }} /></div>
                    <span className="font-mono text-right">{x.v}</span>
                  </div>
                ))}
              </div>
              <p className="text-[11px] text-muted-foreground mt-3 flex gap-1.5"><Info size={13} className="shrink-0 mt-0.5" />Links from suppliers' own filings (“X accounted for 20% of revenue”) are matched directly and don't pass through the AI, so they aren't counted here.</p>
              <div className="mt-3 text-xs">
                <div className="text-[10px] uppercase tracking-wider text-muted-foreground mb-1">Stored links by source</div>
                <div className="flex flex-wrap gap-1.5">{s.relationships_by_source.map((r: any) => <span key={r.source + r.status} className="chip">{r.source} · {r.status} <b className="font-mono">{r.count}</b></span>)}</div>
              </div>
            </div>
          </div>

          <div className="panel p-4 space-y-3">
            <div className="flex flex-wrap items-center gap-3">
              <div className="font-semibold text-sm flex-1">Benchmark — 10 fixed questions</div>
              <select value={ticker} onChange={(e) => setTicker(e.target.value)} className="rounded-lg bg-background/60 border border-border/70 px-2 py-1 text-xs font-mono" aria-label="Company">
                {wl.symbols.map((t) => <option key={t}>{t}</option>)}
              </select>
              <button onClick={start} disabled={busy || !ticker} className="rounded-lg bg-primary text-primary-foreground text-xs font-semibold px-3 py-1.5 flex items-center gap-1.5 disabled:opacity-50">
                <Play size={12} /> {busy ? 'Running… (about a minute)' : 'Run benchmark'}
              </button>
            </div>
            <p className="text-[11px] text-muted-foreground">Uses 10 AI requests. Known-fact questions are scored against the value Oracle computes from the filings (within 2%); “should decline” questions pass when the AI says it can't answer.</p>
            {run && (
              <>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                  <Stat label={`Accuracy on known facts (${run.summary.scored_questions})`} value={pct(run.summary.accuracy_on_known_facts, 0)} tone={tone(run.summary.accuracy_on_known_facts, 0.8, 0.6)} />
                  <Stat label="Answered with citations" value={pct(run.summary.answered_with_citations, 0)} tone={tone(run.summary.answered_with_citations)} />
                  <Stat label="Clean numbers" value={pct(run.summary.clean_numbers, 0)} tone={tone(run.summary.clean_numbers)} />
                  <Stat label="Median latency" value={`${(run.summary.median_latency_ms / 1000).toFixed(1)}s`} hint={`${run.ticker} · ${run.model || ''}`} />
                </div>
                <div className="overflow-x-auto">
                  <table className="w-full text-xs">
                    <thead><tr className="text-muted-foreground"><th className="text-left font-medium py-1.5">Question</th><th className="text-left font-medium">Type</th><th className="text-center font-medium">Result</th><th className="text-right font-medium">Citations</th><th className="text-left font-medium pl-3">Unsupported numbers</th></tr></thead>
                    <tbody>
                      {run.results.map((x: any) => (
                        <tr key={x.id} className="border-t border-border/50 align-top" title={x.answer}>
                          <td className="py-1.5 pr-3">{x.question}</td>
                          <td className="text-muted-foreground whitespace-nowrap">{x.category}</td>
                          <td className="text-center">{'correct' in x ? (x.correct ? <CheckCircle2 size={14} className="inline text-success" /> : <XCircle size={14} className="inline text-destructive" />) : <span className="text-muted-foreground">—</span>}</td>
                          <td className="text-right font-mono">{x.citations}</td>
                          <td className="pl-3 font-mono text-warning">{x.unsupported.join(', ')}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                  <p className="text-[11px] text-muted-foreground mt-2">Hover a row to read the full answer.</p>
                </div>
              </>
            )}
          </div>
        </>
      )}
    </div>
  );
}
