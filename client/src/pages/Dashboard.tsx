import { useState, useEffect, useRef, useCallback } from 'react';
import { api } from '@/lib/api';
import { AutoTerm } from '@/components/PlainText';
import {
  ComposedChart, Bar, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid, ReferenceLine,
} from 'recharts';
import { Zap, Newspaper, ShieldAlert, TrendingUp, TrendingDown, Radio, Link2, Activity, Flame } from 'lucide-react';
import Chat from '@/pages/Chat';
import { format } from 'date-fns';

interface Ticker { symbol: string; name: string; price?: number; change?: number }
interface CandleData {
  timestamp: string; open: number; high: number; low: number; close: number; volume: number;
  RSI?: number; VWAP?: number; MACD?: number; BandWidth?: number;
}
interface Stats { ratios: Array<{ key: string; label: string; value: string | number }> }
interface Alert { created_at: string; ticker: string; message: string }
interface NewsItem { url: string; headline: string; ticker: string; sentiment_score: number; published_at?: string }

// ---------------------------------------------------------------- helpers
const timeOf = (s?: string) => {
  if (!s) return '';
  const d = new Date(s);
  return isNaN(d.getTime()) ? '' : format(d, 'HH:mm');
};

const alertStyle = (msg: string) => {
  const m = msg.toLowerCase();
  if (m.includes('contagion') || m.includes('supply')) return { icon: Link2, cls: 'text-warning bg-warning/10 ring-warning/30' };
  if (m.includes('trap') || m.includes('overbought') || m.includes('breakdown') || m.includes('bearish')) return { icon: ShieldAlert, cls: 'text-destructive bg-destructive/10 ring-destructive/30' };
  if (m.includes('volume') || m.includes('spike') || m.includes('block')) return { icon: Flame, cls: 'text-info bg-info/10 ring-info/30' };
  return { icon: TrendingUp, cls: 'text-success bg-success/10 ring-success/30' };
};

// ---------------------------------------------------------------- chart parts
// eslint-disable-next-line @typescript-eslint/no-explicit-any
const Candle = (props: any) => {
  const { x, y, width, height, payload } = props;
  const { open, close, high, low } = payload;
  const up = close >= open;
  const color = up ? 'hsl(152 70% 46%)' : 'hsl(350 89% 62%)';
  const range = high - low;
  const scale = range === 0 ? 0 : height / range;
  const bodyTop = y + (high - Math.max(open, close)) * scale;
  const bodyH = Math.max(1.2, Math.abs(open - close) * scale);
  const w = Math.max(2, width * 0.7);
  const cx = x + width / 2;
  return (
    <g>
      <line x1={cx} y1={y} x2={cx} y2={y + height} stroke={color} strokeWidth={1} />
      <rect x={cx - w / 2} y={bodyTop} width={w} height={bodyH} rx={1} fill={color} />
    </g>
  );
};

// eslint-disable-next-line @typescript-eslint/no-explicit-any
const ChartTip = ({ active, payload }: any) => {
  if (!active || !payload?.length) return null;
  const d = payload[0].payload as CandleData;
  const row = (k: string, v: string, c = 'text-foreground') => (
    <div className="flex justify-between gap-6"><span className="text-muted-foreground">{k}</span><span className={`font-mono ${c}`}>{v}</span></div>
  );
  return (
    <div className="panel px-3 py-2 text-xs space-y-0.5 min-w-[150px]">
      <div className="font-mono text-muted-foreground mb-1">{format(new Date(d.timestamp), 'MMM dd HH:mm')}</div>
      {row('Open', d.open.toFixed(2))}
      {row('High', d.high.toFixed(2))}
      {row('Low', d.low.toFixed(2))}
      {row('Close', d.close.toFixed(2), d.close >= d.open ? 'text-success' : 'text-destructive')}
      {row('Volume', new Intl.NumberFormat('en-US', { notation: 'compact' }).format(d.volume))}
    </div>
  );
};

const Indicator = ({ label, value, tone, hint }: { label: string; value?: number; tone: string; hint: string }) => {
  if (value === undefined || value === null || isNaN(Number(value))) return null;
  return (
    <div className="rounded-xl border border-border/70 bg-background/40 px-3 py-2 min-w-[92px]">
      <div className="text-[10px] uppercase tracking-wider text-muted-foreground"><AutoTerm text={label} /></div>
      <div className={`font-mono font-bold text-sm ${tone}`}>{Number(value).toFixed(2)}</div>
      <div className="text-[10px] text-muted-foreground">{hint}</div>
    </div>
  );
};

// ---------------------------------------------------------------- page
export default function Dashboard() {
  const [activeTicker, setActiveTicker] = useState<string | null>(null);
  const [timeframe, setTimeframe] = useState('1D');
  const [tickers, setTickers] = useState<Ticker[]>([]);
  const [data, setData] = useState<CandleData[]>([]);
  const [dataKey, setDataKey] = useState('');
  const [stats, setStats] = useState<Stats | null>(null);
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [news, setNews] = useState<NewsItem[]>([]);
  const [flash, setFlash] = useState<'' | 'flash-up' | 'flash-down'>('');
  const [feed, setFeed] = useState<{ status: string; detail: string; last_bar_utc?: string | null } | null>(null);
  const prevPrice = useRef<number | null>(null);

  useEffect(() => {
    const load = () => api.getActiveTickers().then((res) => {
      setTickers(res.data);
      setActiveTicker((cur) => cur ?? (res.data[0]?.symbol || null));
    }).catch(() => {});
    load();
    const id = setInterval(load, 5000);
    return () => clearInterval(id);
  }, []);

  const fetchFast = useCallback(async () => {
    if (!activeTicker) return;
    const tf = timeframe === '1D' ? '1Min' : timeframe;
    const [c, a] = await Promise.allSettled([api.getCandles(activeTicker, tf), api.getAlerts(activeTicker)]);
    if (c.status === 'fulfilled') {
      const rows = Array.isArray(c.value.data) ? c.value.data : c.value.data.data || [];
      if (rows.length) { setData(rows); setDataKey(`${activeTicker}-${timeframe}`); }
    }
    if (a.status === 'fulfilled') setAlerts(Array.isArray(a.value.data) ? a.value.data : []);
  }, [activeTicker, timeframe]);

  const fetchSlow = useCallback(async () => {
    if (!activeTicker) return;
    const [n, s] = await Promise.allSettled([api.getNews(activeTicker), api.getStats(activeTicker)]);
    if (n.status === 'fulfilled') setNews(Array.isArray(n.value.data) ? n.value.data : []);
    if (s.status === 'fulfilled') setStats(s.value.data);
  }, [activeTicker]);

  useEffect(() => {
    if (!activeTicker) return;
    prevPrice.current = null;
    fetchFast(); fetchSlow();
    const f = setInterval(fetchFast, 5000);
    const s = setInterval(fetchSlow, 60000);
    return () => { clearInterval(f); clearInterval(s); };
  }, [activeTicker, timeframe, fetchFast, fetchSlow]);

  // Real feed state for the badge: LIVE only when bars are actually arriving.
  useEffect(() => {
    if (!activeTicker) return;
    const load = () => api.getSystemStatus(activeTicker)
      .then((r) => setFeed(r.data.agents.find((a: { key: string }) => a.key === 'price') || null))
      .catch(() => setFeed(null));
    load();
    const id = setInterval(load, 30000);
    return () => clearInterval(id);
  }, [activeTicker]);

  const stale = dataKey !== `${activeTicker}-${timeframe}`;
  const latest = data.length && !stale ? data[data.length - 1] : null;
  const first = data.length ? data[0] : null;
  const change = latest && first ? ((latest.close - first.open) / first.open) * 100 : 0;

  useEffect(() => {
    if (!latest) return;
    if (prevPrice.current !== null && latest.close !== prevPrice.current) {
      setFlash(latest.close > prevPrice.current ? 'flash-up' : 'flash-down');
      const t = setTimeout(() => setFlash(''), 900);
      prevPrice.current = latest.close;
      return () => clearTimeout(t);
    }
    prevPrice.current = latest.close;
  }, [latest?.close]); // eslint-disable-line react-hooks/exhaustive-deps

  const lows = data.map((d) => d.low), highs = data.map((d) => d.high);
  const minP = Math.min(...lows), maxP = Math.max(...highs);
  const pad = (maxP - minP) * 0.08;
  const maxVol = Math.max(...data.map((d) => d.volume), 1);
  const chartData = data.map((d) => ({ ...d, range: [d.low, d.high] }));

  const uniqueAlerts = alerts.filter((a, i, self) => i === self.findIndex((t) => t.message === a.message)).slice(0, 20);
  const uniqueNews = news.filter((n, i, self) => i === self.findIndex((t) => t.headline.trim() === n.headline.trim())).slice(0, 20);
  const current = tickers.find((t) => t.symbol === activeTicker);

  return (
    <div className="grid grid-cols-1 xl:grid-cols-[minmax(0,1fr)_380px] gap-5">
      <div className="flex flex-col gap-5 min-w-0">
        {/* ticker tabs */}
        <div className={`flex gap-2 ${tickers.length > 8 ? 'overflow-x-auto scroll-panel pb-1 [&>button]:shrink-0' : 'flex-wrap'}`} data-tour="tickers">
          {tickers.map((t) => {
            const on = t.symbol === activeTicker;
            return (
              <button key={t.symbol} data-ticker={t.symbol} onClick={() => setActiveTicker(t.symbol)}
                className={`flex items-center gap-3 rounded-xl px-3.5 py-2 text-left transition-all border ${on ? 'bg-primary/15 border-primary/50 glow-primary' : 'bg-card/70 border-border/70 hover:border-primary/40'}`}>
                <span className="font-bold text-sm">{t.symbol}</span>
                {typeof t.price === 'number' && (
                  <span className="font-mono text-xs leading-tight">
                    <span className="text-muted-foreground">${t.price.toFixed(2)}</span>{' '}
                    <span className={t.change! >= 0 ? 'text-success' : 'text-destructive'}>{t.change! >= 0 ? '+' : ''}{t.change!.toFixed(2)}%</span>
                  </span>
                )}
              </button>
            );
          })}
        </div>

        {/* quote header + chart */}
        <div className="panel">
          <div className="flex flex-wrap items-center justify-between gap-4 px-5 pt-4">
            <div className="flex items-end gap-4">
              <div>
                <div className="flex items-center gap-2 text-xs text-muted-foreground" title={feed?.detail}>
                  {(() => {
                    const lastBar = feed?.last_bar_utc ? format(new Date(feed.last_bar_utc.replace(' ', 'T') + 'Z'), 'MMM d, HH:mm') : null;
                    if (!feed) return <><span className="w-2 h-2 rounded-full bg-muted-foreground" /> {current?.name || activeTicker}</>;
                    if (feed.status === 'ok') return <><span className="relative flex w-2 h-2"><span className="absolute inset-0 rounded-full bg-success animate-ping opacity-70" /><span className="relative w-2 h-2 rounded-full bg-success" /></span>LIVE · {current?.name || activeTicker}</>;
                    if (feed.status === 'idle') return <><span className="w-2 h-2 rounded-full bg-info" />MARKET CLOSED · last bar {lastBar || '—'} · {current?.name || activeTicker}</>;
                    return <><span className="w-2 h-2 rounded-full bg-destructive" /><span className="text-destructive">STALE DATA</span> · last bar {lastBar || '—'} · {current?.name || activeTicker}</>;
                  })()}
                </div>
                <div className="flex items-baseline gap-3 mt-0.5">
                  <span className="text-3xl font-bold tracking-tight">{activeTicker}</span>
                  {latest && <span className={`font-mono text-3xl font-bold rounded-md px-1 ${flash}`}>${latest.close.toFixed(2)}</span>}
                  {latest && (
                    <span className={`flex items-center gap-1 font-mono text-sm font-semibold ${change >= 0 ? 'text-success' : 'text-destructive'}`}>
                      {change >= 0 ? <TrendingUp size={16} /> : <TrendingDown size={16} />}{change >= 0 ? '+' : ''}{change.toFixed(2)}%
                    </span>
                  )}
                </div>
              </div>
            </div>
            <div className="flex items-center gap-1 rounded-xl bg-background/60 border border-border/70 p-1">
              {['1D', '1W', '1M'].map((tf) => (
                <button key={tf} data-tf={tf} onClick={() => setTimeframe(tf)}
                  className={`px-3 py-1 text-xs font-semibold rounded-lg transition-colors ${timeframe === tf ? 'bg-primary text-primary-foreground' : 'text-muted-foreground hover:text-foreground'}`}>{tf}</button>
              ))}
            </div>
          </div>

          <div className="flex flex-wrap gap-2 px-5 pt-4">
            {latest && (
              <>
                <Indicator label="RSI 14" value={latest.RSI} tone="text-foreground"
                  hint="0–100: share of recent moves that were up" />
                <Indicator label="MACD" value={latest.MACD} tone={Number(latest.MACD) >= 0 ? 'text-success' : 'text-destructive'} hint="short-term minus longer-term average price" />
                <Indicator label="VWAP" value={latest.VWAP} tone={latest.close >= Number(latest.VWAP) ? 'text-success' : 'text-destructive'} hint={latest.close >= Number(latest.VWAP) ? "price is above today's average trade price" : "price is below today's average trade price"} />
                <Indicator label="BB width" value={latest.BandWidth} tone="text-info" hint="width of the recent price range, %" />
              </>
            )}
            <div className="flex-1" />
          </div>

          <div className={`h-[330px] px-2 pb-2 pt-3 transition-opacity duration-300 ${stale ? 'opacity-30' : ''}`}>
            {data.length > 0 ? (
              <ResponsiveContainer width="100%" height="100%">
                <ComposedChart data={chartData} margin={{ top: 4, right: 8, bottom: 0, left: 0 }}>
                  <defs>
                    <linearGradient id="vol" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor="hsl(248 92% 68%)" stopOpacity={0.45} />
                      <stop offset="100%" stopColor="hsl(248 92% 68%)" stopOpacity={0.05} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid stroke="hsl(var(--border))" strokeDasharray="3 6" vertical={false} />
                  <XAxis dataKey="timestamp" tickFormatter={(t) => format(new Date(t), timeframe === '1D' ? 'HH:mm' : 'MMM dd')}
                    tick={{ fill: 'hsl(var(--muted-foreground))', fontSize: 11 }} axisLine={false} tickLine={false} minTickGap={40} />
                  <YAxis yAxisId="p" domain={[minP - pad, maxP + pad]} orientation="right" tick={{ fill: 'hsl(var(--muted-foreground))', fontSize: 11 }}
                    tickFormatter={(v) => v.toFixed(0)} axisLine={false} tickLine={false} width={44} />
                  <YAxis yAxisId="v" domain={[0, maxVol * 4.5]} hide />
                  <Tooltip content={<ChartTip />} cursor={{ stroke: 'hsl(var(--muted-foreground))', strokeDasharray: '3 3' }} />
                  <Bar yAxisId="v" dataKey="volume" fill="url(#vol)" isAnimationActive={false} />
                  <Line yAxisId="p" dataKey="VWAP" stroke="hsl(38 96% 58%)" strokeWidth={1.4} strokeDasharray="4 4" dot={false} isAnimationActive={false} />
                  <Bar yAxisId="p" dataKey="range" shape={<Candle />} isAnimationActive={false} />
                  {latest && (
                    <ReferenceLine yAxisId="p" y={latest.close} stroke={change >= 0 ? 'hsl(152 70% 46%)' : 'hsl(350 89% 62%)'} strokeDasharray="2 4"
                      label={{ value: latest.close.toFixed(2), position: 'insideRight', fill: '#fff', fontSize: 11, className: 'font-mono' }} />
                  )}
                </ComposedChart>
              </ResponsiveContainer>
            ) : (
              <div className="h-full grid place-items-center text-muted-foreground text-sm">Waiting for market data…</div>
            )}
          </div>
          <div className="flex gap-4 px-5 pb-4 text-[11px] text-muted-foreground">
            <span className="flex items-center gap-1.5"><span className="w-3 h-0.5 bg-warning" /> VWAP</span>
            <span className="flex items-center gap-1.5"><span className="w-2.5 h-2.5 rounded-sm bg-primary/40" /> Volume</span>
            <span className="flex items-center gap-1.5"><Radio size={12} /> {feed?.status === 'ok' ? 'updates every 5s' : feed?.detail || 'checking feed…'}</span>
          </div>
        </div>

        {/* fundamentals */}
        {stats && stats.ratios.length > 0 && (
          <div className="grid grid-cols-3 md:grid-cols-6 gap-3">
            {stats.ratios.map((r) => (
              <div key={r.key} className="panel px-3 py-2.5">
                <div className="text-[10px] uppercase tracking-wider text-muted-foreground">{r.label}</div>
                <div className="font-mono font-bold text-base mt-0.5">{r.value}</div>
              </div>
            ))}
          </div>
        )}

        {/* alerts + news */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
          <div className="panel flex flex-col" data-tour="alerts">
            <div className="panel-head">
              <span className="flex items-center gap-2"><Zap size={16} className="text-warning" /> Live signals</span>
              <span className="chip text-muted-foreground"><Activity size={12} /> alert engine</span>
            </div>
            <div className="px-3 pb-3 space-y-2 overflow-y-auto scroll-panel h-[230px]">
              {uniqueAlerts.map((a) => {
                const s = alertStyle(a.message);
                return (
                  <div key={a.message + a.created_at} className="fade-up flex gap-3 items-start rounded-xl bg-background/40 border border-border/60 p-2.5">
                    <span className={`grid place-items-center w-7 h-7 rounded-lg ring-1 shrink-0 ${s.cls}`}><s.icon size={14} /></span>
                    <div className="flex-1 text-[13px] leading-snug">{a.message}</div>
                    <span className="font-mono text-[11px] text-muted-foreground">{timeOf(a.created_at)}</span>
                  </div>
                );
              })}
              {uniqueAlerts.length === 0 && <p className="text-center text-muted-foreground py-8 text-sm">No live alerts yet.</p>}
            </div>
          </div>

          <div className="panel flex flex-col" data-tour="news">
            <div className="panel-head">
              <span className="flex items-center gap-2"><Newspaper size={16} className="text-info" /> Latest news</span>
              <span className="chip text-muted-foreground">headlines link to the publisher</span>
            </div>
            <div className="px-3 pb-3 space-y-2 overflow-y-auto scroll-panel h-[230px]">
              {uniqueNews.map((n, i) => (
                <a key={i} href={n.url} target="_blank" rel="noreferrer" className="fade-up block rounded-xl bg-background/40 border border-border/60 p-2.5 hover:border-primary/40 transition-colors">
                  <div className="text-[13px] leading-snug">{n.headline}</div>
                  <div className="flex justify-between items-center mt-1.5 text-[11px]">
                    <span className="text-muted-foreground font-mono">{n.ticker} · {timeOf(n.published_at)}</span>
                    <span className="text-muted-foreground truncate max-w-[45%]">{(() => { try { return new URL(n.url).hostname.replace('www.', ''); } catch { return ''; } })()}</span>
                  </div>
                </a>
              ))}
              {uniqueNews.length === 0 && <p className="text-center text-muted-foreground py-8 text-sm">No news yet.</p>}
            </div>
          </div>
        </div>
      </div>

      {/* AI analyst */}
      <div className="xl:sticky xl:top-0 h-[calc(100vh-7rem)] min-h-[640px]" data-tour="analyst">
        <Chat isEmbedded activeTicker={activeTicker} />
      </div>
    </div>
  );
}
