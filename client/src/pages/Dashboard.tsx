import { useState, useEffect } from 'react';
import { api } from '@/lib/api';
import RatioPanel from '@/components/RatioPanel';
import { ComposedChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid, Cell } from 'recharts';
import { Activity, Newspaper, TrendingUp, TrendingDown, Waves, Activity as ActivityIcon } from 'lucide-react';
import Chat from '@/pages/Chat';
import { format } from 'date-fns';

interface Ticker {
  symbol: string;
  name: string;
}

interface CandleData {
  timestamp: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  RSI?: number;
  VWAP?: number;
  MACD?: number;
  BandWidth?: number;
}

interface Stats {
  risk_score: number;
  ratios: Array<{ key: string; label: string; value: string | number }>;
}

interface Alert {
  created_at: string;
  ticker: string;
  message: string;
}

interface NewsItem {
  url: string;
  headline: string;
  ticker: string;
  sentiment_score: number;
}

// --- CANDLESTICK SHAPE ---
const CandlestickShape = (props: any) => {
  const { x, y, width, height, payload } = props;
  const { open, close, high, low } = payload;
  const isUp = close > open;
  const color = isUp ? '#22c55e' : '#ef4444';

  const range = high - low;
  const scale = range === 0 ? 0 : height / range;
  
  const bodyTop = y + (high - Math.max(open, close)) * scale;
  const bodyHeight = Math.abs(open - close) * scale;
  const effectiveBodyHeight = Math.max(1, bodyHeight);

  return (
    <g stroke={color} fill={color} strokeWidth="1">
      <line x1={x + width / 2} y1={y} x2={x + width / 2} y2={y + height} />
      <rect
        x={x}
        y={bodyTop}
        width={width}
        height={effectiveBodyHeight}
        fill={color}
        strokeWidth="0" 
      />
    </g>
  );
};

// --- CUSTOM TOOLTIP ---
const CustomTooltip = ({ active, payload, label }: any) => {
  if (active && payload && payload.length) {
    const data = payload[0].payload; 
    return (
      <div className="bg-card border border-border p-3 rounded shadow-xl text-sm">
        <p className="font-mono text-muted-foreground mb-2 border-b border-border pb-1">
          {label}
        </p>
        <div className="flex flex-col gap-1">
          <div className="flex justify-between gap-4">
            <span className="text-muted-foreground font-semibold">Price:</span>
            <span className="font-mono font-bold text-foreground">
              ${Number(data.close).toFixed(2)}
            </span>
          </div>
          <div className="flex justify-between gap-4">
            <span className="text-muted-foreground font-semibold">Volume:</span>
            <span className="font-mono font-bold text-foreground">
              {new Intl.NumberFormat('en-US').format(data.volume)}
            </span>
          </div>
        </div>
      </div>
    );
  }
  return null;
};

// --- INDICATOR BADGE ---
const IndicatorBadge = ({ label, value, type, comparisonValue }: any) => {
  if (value === undefined || value === null || value === 'N/A') return null;
  
  let colorClass = 'text-blue-400';
  const numVal = parseFloat(value);

  if (!isNaN(numVal)) {
    if (type === 'RSI') {
      if (numVal > 70) colorClass = 'text-red-500';
      else if (numVal < 30) colorClass = 'text-green-500';
    } 
    else if (type === 'MACD') {
      colorClass = numVal > 0 ? 'text-green-500' : 'text-red-500';
    } 
    else if (type === 'VWAP' && comparisonValue) {
      colorClass = comparisonValue > numVal ? 'text-green-500' : 'text-red-500';
    }
  }

  return (
    <div className="flex items-center gap-1.5 text-xs bg-card border border-border px-2 py-1 rounded">
      <span className="font-bold text-muted-foreground">{label}:</span>
      <span className={`font-mono font-bold ${colorClass}`}>
        {typeof value === 'number' ? value.toFixed(2) : value}
        {type === 'BW' ? '%' : ''}
      </span>
    </div>
  );
};

export default function Dashboard() {
  const [activeTicker, setActiveTicker] = useState<string | null>(null);
  const [timeframe, setTimeframe] = useState('1D');
  const [tickers, setTickers] = useState<Ticker[]>([]);
  const [data, setData] = useState<CandleData[]>([]);
  const [stats, setStats] = useState<Stats | null>(null);
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [news, setNews] = useState<NewsItem[]>([]);

  const latest = data.length > 0 ? data[data.length - 1] : null;

  useEffect(() => {
    api.getActiveTickers().then(res => {
      setTickers(res.data);
      if (res.data.length > 0) setActiveTicker(res.data[0].symbol);
    }).catch(() => {});
  }, []);

  useEffect(() => {
    if (!activeTicker) return;
    const fetchData = async () => {
      try {
        const candles = await api.getCandles(activeTicker, timeframe);
        const statData = await api.getStats(activeTicker);
        const alertData = await api.getAlerts(activeTicker || undefined);
        const newsData = await api.getNews(activeTicker);
        
        setData(candles.data.data || []);
        setStats(statData.data);
        setAlerts(alertData.data || []);
        setNews(newsData.data || []);
      } catch (e) { console.error(e); }
    };
    fetchData();
    const interval = setInterval(fetchData, 5000);
    return () => clearInterval(interval);
  }, [activeTicker, timeframe]);
  
  const formatTimestamp = (timestamp: string) => {
    try {
      if (timeframe === '1D') return format(new Date(timestamp), 'HH:mm');
      return format(new Date(timestamp), 'MMM dd');
    } catch (e) { return timestamp; }
  };

  const chartData = data.map(d => ({
    ...d,
    candleRange: [d.low, d.high] 
  }));

  return (
    <div className="grid grid-cols-1 lg:grid-cols-4 gap-6 min-h-full"> 
      {/* LEFT COLUMN */}
      <div className="lg:col-span-3 flex flex-col gap-6">
        
        {/* HEADER */}
        <div className="bg-card p-4 rounded-xl border border-border flex flex-col xl:flex-row justify-between items-center gap-4">
          <div className="flex gap-4 items-center w-full md:w-auto">
            <select 
              className="bg-background border border-border rounded px-3 py-2 text-foreground font-mono focus:outline-none focus:border-primary font-bold"
              value={activeTicker || ''}
              onChange={(e) => setActiveTicker(e.target.value)}
            >
              {tickers.length === 0 && <option>No tickers</option>}
              {tickers.map(t => <option key={t.symbol} value={t.symbol}>{t.symbol}</option>)}
            </select>
            
            <div className="flex bg-background rounded border border-border p-1">
              {['1D', '1W', '1M'].map(tf => (
                <button 
                  key={tf}
                  onClick={() => setTimeframe(tf)}
                  className={`px-3 py-1 text-xs font-bold rounded transition-colors ${timeframe === tf ? 'bg-primary text-primary-foreground' : 'text-muted-foreground hover:text-foreground'}`}
                >
                  {tf}
                </button>
              ))}
            </div>

            {latest && latest.close != null && (
              <div className="text-2xl font-bold font-mono text-primary ml-2">
                ${Number(latest.close).toFixed(2)}
              </div>
            )}
          </div>
          
          {/* INDICATORS */}
          <div className="flex flex-wrap justify-center gap-2 items-center w-full xl:w-auto">
            {latest && (
              <>
                <IndicatorBadge label="RSI" value={latest.RSI} type="RSI" />
                <IndicatorBadge label="MACD" value={latest.MACD} type="MACD" />
                <IndicatorBadge label="VWAP" value={latest.VWAP} type="VWAP" comparisonValue={latest.close} />
                <IndicatorBadge label="BW" value={latest.BandWidth} type="BW" />
              </>
            )}
            
            {stats && (
              <div className={`ml-2 px-3 py-1 rounded border font-bold text-xs flex items-center gap-2 ${stats.risk_score > 50 ? 'border-destructive bg-destructive/20 text-destructive' : 'border-[hsl(var(--success))] bg-[hsl(var(--success))]/20 text-[hsl(var(--success))]'}`}>
                <Activity size={14}/> Risk: {stats.risk_score}
              </div>
            )}
          </div>
        </div>

        <div className="bg-card p-4 rounded-xl border border-border">
          {stats ? <RatioPanel ratios={stats.ratios} /> : <div className="text-muted-foreground text-center py-4">Loading Fundamentals...</div>}
        </div>

        <div className="bg-card p-4 rounded-xl border border-border h-[500px]">
          <ResponsiveContainer width="100%" height="100%">
            <ComposedChart data={chartData}>
              <CartesianGrid stroke="hsl(var(--border))" strokeDasharray="3 3" vertical={false} opacity={0.5} />
              <XAxis dataKey="timestamp" tickFormatter={formatTimestamp} tick={{fill: 'hsl(var(--muted-foreground))', fontSize: 12}} minTickGap={30} />
              <YAxis domain={['auto', 'auto']} orientation="right" tick={{fill: 'hsl(var(--muted-foreground))', fontSize: 12}} tickFormatter={(val) => val.toFixed(2)} />
              <Tooltip content={<CustomTooltip />} cursor={{ stroke: 'hsl(var(--muted-foreground))', strokeWidth: 1, strokeDasharray: '3 3' }}/>
              <Bar dataKey="candleRange" shape={<CandlestickShape />} isAnimationActive={false} />
            </ComposedChart>
          </ResponsiveContainer>
        </div>
        
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <div className="bg-card p-4 rounded-xl border border-border">
            <div className="card-header-custom panel-title">⏰ Live Alerts</div>
            <div className="mt-3 scroll-panel overflow-y-auto" style={{maxHeight: '220px', minHeight: '180px'}}>
              {alerts.map((a, i) => (
                <div key={i} className="text-sm border-b border-border pb-2 pt-2">
                  <span className="text-[hsl(var(--warning))] font-mono text-xs block">{new Date(a.created_at).toLocaleTimeString()}</span>
                  <span className="font-bold text-foreground">{a.ticker}</span>: <span className="text-muted-foreground">{a.message}</span>
                </div>
              ))}
              {alerts.length === 0 && <p className="text-center text-muted-foreground py-4">No live alerts.</p>}
            </div>
          </div>

          <div className="bg-card p-4 rounded-xl border border-border">
            <div className="card-header-custom panel-title"><Newspaper size={18} /> Market News</div>
            <div className="mt-3 scroll-panel overflow-y-auto" style={{maxHeight: '220px', minHeight: '180px'}}>
              {news.map((n, i) => (
                <div key={i} className="border-b border-border pb-2 pt-2">
                  <a href={n.url} target="_blank" rel="noreferrer" className="text-sm font-medium text-primary hover:underline block">{n.headline}</a>
                  <div className="flex justify-between mt-1">
                    <span className="text-xs text-muted-foreground">{n.ticker}</span>
                    <span className={`text-xs ${n.sentiment_score > 0 ? 'text-[hsl(var(--success))]' : 'text-destructive'}`}>Score: {n.sentiment_score}</span>
                  </div>
                </div>
              ))}
              {news.length === 0 && <p className="text-center text-muted-foreground py-4">No news available.</p>}
            </div>
          </div>
        </div>
      </div>

      {/* RIGHT COLUMN (AI Analyst) - INCREASED HEIGHT */}
      <div className="lg:col-span-1 h-[950px]"> {/* Changed 800px -> 950px */}
        <div className="bg-card rounded-xl border border-border overflow-hidden h-full flex flex-col">
          <div className="bg-primary text-primary-foreground p-3 font-bold text-center shrink-0">🤖 AI Analyst</div>
          <div className="flex-1 overflow-hidden min-h-0">
            <Chat isEmbedded={true} activeTicker={activeTicker} />
          </div>
        </div>
      </div>
    </div>
  );
}