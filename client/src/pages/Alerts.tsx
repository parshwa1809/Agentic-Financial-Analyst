/* eslint-disable @typescript-eslint/no-explicit-any */
import { useEffect, useState, type ElementType } from 'react';
import { Bell, CheckCheck, RefreshCw, ExternalLink, FileText, Link2, TrendingUp, TrendingDown, Newspaper, CalendarClock, Sunrise, AlertTriangle } from 'lucide-react';
import { api } from '@/lib/api';
import PlainText from '@/components/PlainText';
import { signedPct, usd, errMsg } from '@/lib/format';
import { PageHeader, ErrorBox, Loading, Tabs } from '@/components/ResearchBits';
import { useWatchlist } from '@/hooks/useWatchlist';

type Tab = 'events' | 'brief';
const SEV: Record<string, string> = { high: 'bg-destructive', warn: 'bg-warning', info: 'bg-info' };
const KIND_ICON: Record<string, ElementType> = {
  supplier_move: Link2, customer_move: Link2, competitor_move: Link2, price_move: TrendingUp, filing: FileText, earnings: CalendarClock, news_risk: Newspaper,
};
const KIND_LABEL: Record<string, string> = {
  supplier_move: 'Supplier move', customer_move: 'Customer move', competitor_move: 'Competitor move', price_move: 'Price move',
  filing: 'SEC filing', earnings: 'Earnings', news_risk: 'High-risk news',
};

export default function Alerts() {
  const wl = useWatchlist();
  const [tab, setTab] = useState<Tab>('events');
  const [events, setEvents] = useState<any[] | null>(null);
  const [filter, setFilter] = useState('');
  const [unreadOnly, setUnreadOnly] = useState(false);
  const [brief, setBrief] = useState<any>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notify, setNotify] = useState(typeof Notification !== 'undefined' && Notification.permission === 'granted');

  const load = () => api.getEvents({ ticker: filter || undefined, unread_only: unreadOnly, limit: 200 })
    .then((r) => setEvents(r.data)).catch((e) => setError(errMsg(e)));
  useEffect(() => { load(); const id = setInterval(load, 30000); return () => clearInterval(id); }, [filter, unreadOnly]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { if (tab === 'brief' && !brief) api.getBrief().then((r) => setBrief(r.data)).catch((e) => setError(errMsg(e))); }, [tab, brief]);

  const scan = async () => { setBusy(true); try { await api.scanAlerts(); await load(); } catch (e) { setError(errMsg(e)); } setBusy(false); };
  const readAll = async () => { await api.markAllAlertsRead(); load(); };
  const read = async (id: number) => { await api.markAlertRead(id); setEvents((ev) => ev?.map((e) => (e.id === id ? { ...e, read_at: 'now' } : e)) || null); };
  const enableNotify = async () => { if (typeof Notification === 'undefined') return; setNotify((await Notification.requestPermission()) === 'granted'); };

  return (
    <div className="space-y-5">
      <PageHeader icon={Bell} title="Alerts & brief"
        subtitle="What changed for your companies and the companies they do business with: big price moves, new official reports to the SEC, upcoming results dates and news the AI tagged as about risks, each with the evidence behind it.">
        <div className="flex gap-2 flex-wrap">
          {!notify && typeof Notification !== 'undefined' && <button onClick={enableNotify} className="chip hover:text-foreground"><Bell size={12} /> Browser notifications</button>}
          <button onClick={scan} disabled={busy} className="chip hover:text-foreground disabled:opacity-50"><RefreshCw size={12} className={busy ? 'animate-spin' : ''} /> Check now</button>
          <button onClick={readAll} className="chip hover:text-foreground"><CheckCheck size={12} /> Mark all read</button>
        </div>
      </PageHeader>
      <Tabs tabs={[{ key: 'events' as Tab, label: 'Events' }, { key: 'brief' as Tab, label: 'Daily brief' }]} value={tab} onChange={(t) => setTab(t as Tab)} />
      {error && <ErrorBox message={error} />}

      {tab === 'events' && (
        <>
          <div className="flex flex-wrap gap-1.5 items-center">
            <button onClick={() => setFilter('')} className={`rounded-lg px-2.5 py-1 text-xs font-semibold border ${!filter ? 'bg-primary/15 border-primary/60' : 'border-border/70 text-muted-foreground'}`}>All</button>
            {wl.symbols.map((t) => (
              <button key={t} onClick={() => setFilter(t)} className={`rounded-lg px-2.5 py-1 text-xs font-bold font-mono border ${filter === t ? 'bg-primary/15 border-primary/60' : 'border-border/70 text-muted-foreground'}`}>{t}</button>
            ))}
            <label className="ml-auto flex items-center gap-1.5 text-xs text-muted-foreground"><input type="checkbox" checked={unreadOnly} onChange={(e) => setUnreadOnly(e.target.checked)} /> Unread only</label>
          </div>
          {!events && <Loading text="Loading events…" />}
          {events && events.length === 0 && (
            <div className="panel p-8 text-sm text-muted-foreground">No events yet. Oracle checks every 10 minutes for partner moves of 3% or more, new SEC filings, upcoming earnings and high-risk news. Press “Check now” to run it immediately.</div>
          )}
          <div className="space-y-2">
            {events?.map((e) => {
              const Icon = KIND_ICON[e.kind] || Bell;
              const up = typeof e.evidence?.change === 'number' && e.evidence.change > 0;
              return (
                <div key={e.id} onClick={() => !e.read_at && read(e.id)}
                  className={`panel flex gap-3 p-3 cursor-default ${e.read_at ? 'opacity-70' : ''}`}>
                  <span className={`w-1 rounded-full shrink-0 ${SEV[e.severity] || 'bg-muted'}`} />
                  <span className="grid place-items-center w-8 h-8 rounded-lg bg-secondary shrink-0">
                    {e.kind.endsWith('move') && typeof e.evidence?.change === 'number' ? (up ? <TrendingUp size={15} className="text-success" /> : <TrendingDown size={15} className="text-destructive" />) : <Icon size={15} />}
                  </span>
                  <div className="flex-1 min-w-0">
                    <div className="flex flex-wrap items-center gap-2 text-[11px] text-muted-foreground">
                      <span className="font-mono font-bold text-foreground">{e.ticker}</span>
                      <span>{KIND_LABEL[e.kind] || e.kind}</span>
                      <span>· {e.created_at?.slice(0, 16)}</span>
                      {!e.read_at && <span className="rounded-full bg-primary/15 text-primary px-1.5 font-semibold">new</span>}
                    </div>
                    <div className="text-sm font-semibold mt-0.5">{e.title}</div>
                    <div className="text-[12.5px] text-muted-foreground mt-0.5">{e.body}</div>
                    {e.evidence?.quote && (
                      <div className="mt-1.5 text-[11.5px] italic border-l-2 border-border pl-2 text-muted-foreground">
                        “{String(e.evidence.quote).slice(0, 260)}” <span className="not-italic">— {e.evidence.source_type === 'filing' ? '10-K' : e.evidence.source_type}</span>
                      </div>
                    )}
                    {e.evidence?.url && <a href={e.evidence.url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-[11px] text-info hover:underline mt-1"><ExternalLink size={11} /> Source</a>}
                  </div>
                </div>
              );
            })}
          </div>
        </>
      )}

      {tab === 'brief' && (
        brief ? (
          <div className="space-y-4">
            <div className="panel p-4">
              <div className="flex items-center justify-between">
                <div className="font-semibold flex items-center gap-2"><Sunrise size={16} className="text-warning" /> Brief for {brief.day}</div>
                <button onClick={() => { setBrief(null); api.getBrief(true).then((r) => setBrief(r.data)).catch((e) => setError(errMsg(e))); }} className="chip hover:text-foreground"><RefreshCw size={12} /> Regenerate</button>
              </div>
              <PlainText className="text-sm mt-2" text={`${brief.summary}\n\n**What it doesn't tell you:** where prices go next, or whether to buy, hold or sell.`} />
              {brief.unsupported_numbers?.length > 0 && (
                <div className="mt-2 flex gap-1.5 items-start rounded-lg bg-warning/10 text-warning px-2.5 py-1.5 text-[11px]"><AlertTriangle size={13} className="shrink-0 mt-0.5" />Not found in the facts: {brief.unsupported_numbers.join(', ')}</div>
              )}
              <div className="text-[11px] text-muted-foreground mt-2">Written by the AI from the facts below only, then number-checked.</div>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
              {brief.rows.map((x: any) => (
                <div key={x.ticker} className="panel p-4 space-y-2">
                  <div className="flex items-baseline justify-between">
                    <span className="font-mono font-bold text-lg">{x.ticker}</span>
                    {typeof x.change_1d === 'number' && <span className={`font-mono text-sm ${x.change_1d >= 0 ? 'text-success' : 'text-destructive'}`}>{usd(x.close)} {signedPct(x.change_1d)}</span>}
                  </div>
                  {x.events.length > 0 ? x.events.map((e: any, i: number) => (
                    <div key={i} className="flex gap-2 text-xs"><span className={`w-1.5 h-1.5 rounded-full mt-1.5 shrink-0 ${SEV[e.severity]}`} />{e.title}</div>
                  )) : <div className="text-xs text-muted-foreground">No new events in the last 24 h.</div>}
                  {x.top_headline && <a href={x.top_headline.url} target="_blank" rel="noreferrer" className="flex gap-1.5 text-xs text-info hover:underline"><Newspaper size={12} className="shrink-0 mt-0.5" /><span className="line-clamp-2">{x.top_headline.headline}</span></a>}
                </div>
              ))}
            </div>
          </div>
        ) : <Loading text="Writing today's brief…" />
      )}
    </div>
  );
}
