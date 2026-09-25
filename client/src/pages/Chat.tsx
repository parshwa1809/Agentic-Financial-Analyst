import { useState, useEffect, useRef, Fragment } from 'react';
import { Send, Sparkles, Gavel, LineChart, Landmark, ShieldAlert, TrendingUp, TrendingDown, Check } from 'lucide-react';
import { api } from '@/lib/api';

interface Verdict {
  verdict?: string; decision?: string; confidence?: number;
  horizon?: string; time_horizon?: string; analysis?: string; reasoning?: string;
  bull_case?: string; bear_case?: string;
}
type Message =
  | { role: 'user' | 'bot'; content: string }
  | { role: 'council'; ticker: string; result: Verdict };

interface ChatProps { isEmbedded?: boolean; activeTicker?: string | null }

const SUGGESTIONS = ['Is it a buy right now?', 'Who are its key suppliers?', 'Summarize today'];

const AGENTS = [
  { icon: LineChart, name: 'Technical Analyst', task: 'reading RSI, MACD, VWAP…' },
  { icon: Landmark, name: 'Fundamental Analyst', task: 'checking P/E, margins, debt…' },
  { icon: ShieldAlert, name: 'Risk Manager', task: 'scoring news + supply-chain risk…' },
];

/** Minimal **bold** support for LLM answers. */
const Rich = ({ text }: { text: string }) => (
  <>
    {text.split(/(\*\*[^*]+\*\*)/g).map((part, i) =>
      part.startsWith('**') ? <strong key={i} className="font-semibold text-foreground">{part.slice(2, -2)}</strong> : <Fragment key={i}>{part}</Fragment>,
    )}
  </>
);

const verdictTone = (v: string) =>
  v === 'BUY' ? 'text-success bg-success/15 ring-success/40' : v === 'SELL' ? 'text-destructive bg-destructive/15 ring-destructive/40' : 'text-warning bg-warning/15 ring-warning/40';

const CouncilCard = ({ ticker, r }: { ticker: string; r: Verdict }) => {
  const v = (r.verdict || r.decision || 'HOLD').toUpperCase();
  const conf = Math.round((Number(r.confidence) || 0) * 100);
  const bull = r.bull_case && !r.bull_case.startsWith('See full') ? r.bull_case : null;
  const bear = r.bear_case && !r.bear_case.startsWith('See full') ? r.bear_case : null;
  return (
    <div className="fade-up rounded-2xl border border-border/80 bg-background/60 overflow-hidden" data-tour="verdict">
      <div className="flex items-center justify-between px-3.5 py-3 border-b border-border/70">
        <div>
          <div className="text-[10px] uppercase tracking-wider text-muted-foreground">Council verdict · {ticker}</div>
          <div className="text-xs text-muted-foreground mt-0.5">{r.horizon || r.time_horizon}</div>
        </div>
        <span className={`rounded-xl px-3 py-1.5 text-lg font-extrabold tracking-wide ring-1 ${verdictTone(v)}`}>{v}</span>
      </div>
      <div className="px-3.5 pt-3">
        <div className="flex justify-between text-[11px] text-muted-foreground mb-1"><span>Confidence</span><span className="font-mono">{conf}%</span></div>
        <div className="h-1.5 rounded-full bg-muted overflow-hidden">
          <div className="h-full rounded-full bg-gradient-to-r from-primary to-info" style={{ width: `${conf}%`, transition: 'width 1.2s ease' }} />
        </div>
      </div>
      {(bull || bear) && (
        <div className="grid grid-cols-1 gap-2 px-3.5 pt-3">
          {bull && (
            <div className="rounded-xl bg-success/10 border border-success/25 p-2.5 text-[12px] leading-snug">
              <div className="flex items-center gap-1.5 text-success font-semibold mb-1"><TrendingUp size={13} /> Bull case</div>{bull}
            </div>
          )}
          {bear && (
            <div className="rounded-xl bg-destructive/10 border border-destructive/25 p-2.5 text-[12px] leading-snug">
              <div className="flex items-center gap-1.5 text-destructive font-semibold mb-1"><TrendingDown size={13} /> Bear case</div>{bear}
            </div>
          )}
        </div>
      )}
      <div className="px-3.5 py-3 text-[12px] leading-relaxed text-muted-foreground"><Rich text={r.analysis || r.reasoning || ''} /></div>
    </div>
  );
};

export default function Chat({ isEmbedded = false, activeTicker: propTicker }: ChatProps) {
  const [messages, setMessages] = useState<Message[]>([
    { role: 'bot', content: 'Hi! I read live prices, indicators, news and supply-chain data for your watchlist. Ask me anything, or convene the council for a verdict.' },
  ]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState<false | 'chat' | 'council'>(false);
  const [step, setStep] = useState(0);
  const [activeTicker, setActiveTicker] = useState<string | null>(propTicker || null);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (propTicker && propTicker !== activeTicker) setActiveTicker(propTicker);
    else if (!propTicker && !activeTicker) {
      api.getActiveTickers().then((res) => { if (res.data.length > 0) setActiveTicker(res.data[0].symbol); }).catch(() => {});
    }
  }, [propTicker, activeTicker]);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' });
  }, [messages, loading, step]);

  useEffect(() => {
    if (loading !== 'council') return;
    setStep(0);
    const id = setInterval(() => setStep((s) => Math.min(s + 1, AGENTS.length)), 800);
    return () => clearInterval(id);
  }, [loading]);

  const send = async (text?: string) => {
    const userText = (text ?? input).trim();
    if (!userText || loading) return;
    setMessages((p) => [...p, { role: 'user', content: userText }]);
    setInput('');
    setLoading('chat');
    try {
      const res = await api.chat(userText, activeTicker || undefined);
      setMessages((p) => [...p, { role: 'bot', content: res.data.response }]);
    } catch {
      setMessages((p) => [...p, { role: 'bot', content: 'Error connecting to the AI brain.' }]);
    } finally { setLoading(false); }
  };

  const runCouncil = async () => {
    if (!activeTicker || loading) return;
    setMessages((p) => [...p, { role: 'user', content: `Convene the council on ${activeTicker}` }]);
    setLoading('council');
    try {
      const res = await api.runCouncil(activeTicker);
      const result = res.data.result;
      setMessages((p) => [...p, result ? { role: 'council', ticker: activeTicker, result } : { role: 'bot', content: '⚠️ Could not parse the verdict.' }]);
    } catch {
      setMessages((p) => [...p, { role: 'bot', content: 'The council is offline right now.' }]);
    } finally { setLoading(false); }
  };

  return (
    <div className={`panel flex flex-col overflow-hidden ${isEmbedded ? 'h-full' : 'h-[640px] max-w-3xl mx-auto'}`}>
      <div className="flex items-center gap-3 px-4 py-3.5 border-b border-border/70">
        <div className="grid place-items-center w-9 h-9 rounded-xl bg-gradient-to-br from-primary to-info text-white"><Sparkles size={18} /></div>
        <div className="leading-tight flex-1">
          <div className="font-semibold">AI Analyst</div>
          <div className="text-[11px] text-muted-foreground">Local LLM · RAG over live data</div>
        </div>
        {activeTicker && <span className="chip font-mono font-bold">{activeTicker}</span>}
      </div>

      <div ref={scrollRef} className="flex-1 overflow-y-auto scroll-panel p-4 space-y-3 min-h-0" data-tour="chat">
        {messages.map((m, i) =>
          m.role === 'council' ? (
            <CouncilCard key={i} ticker={m.ticker} r={m.result} />
          ) : (
            <div key={i} className={`fade-up flex ${m.role === 'user' ? 'justify-end' : ''}`}>
              <div className={`max-w-[88%] rounded-2xl px-3.5 py-2.5 text-[13px] leading-relaxed whitespace-pre-wrap ${
                m.role === 'user' ? 'bg-primary text-primary-foreground rounded-br-md' : 'bg-secondary/80 border border-border/60 rounded-bl-md'}`}>
                <Rich text={m.content} />
              </div>
            </div>
          ),
        )}

        {loading === 'chat' && (
          <div className="flex"><div className="rounded-2xl rounded-bl-md bg-secondary/80 border border-border/60 px-4 py-3 flex gap-1">
            {[0, 1, 2].map((d) => <span key={d} className="typing-dot w-1.5 h-1.5 rounded-full bg-muted-foreground" style={{ animationDelay: `${d * 0.15}s` }} />)}
          </div></div>
        )}

        {loading === 'council' && (
          <div className="fade-up rounded-2xl border border-border/80 bg-background/60 p-3 space-y-2.5">
            <div className="text-[10px] uppercase tracking-wider text-muted-foreground">Council in session</div>
            {AGENTS.map((a, i) => {
              const done = step > i, live = step === i;
              return (
                <div key={a.name} className={`flex items-center gap-2.5 transition-opacity ${step >= i ? 'opacity-100' : 'opacity-35'}`}>
                  <span className={`grid place-items-center w-7 h-7 rounded-lg ${done ? 'bg-success/15 text-success' : 'bg-primary/15 text-primary'}`}>
                    {done ? <Check size={14} /> : <a.icon size={14} className={live ? 'animate-pulse' : ''} />}
                  </span>
                  <div className="leading-tight text-[12px]">
                    <div className="font-semibold">{a.name}</div>
                    <div className="text-muted-foreground">{done ? 'argument submitted' : a.task}</div>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      <div className="p-3 border-t border-border/70 space-y-2.5">
        <div className="flex gap-1.5 flex-wrap">
          {SUGGESTIONS.map((s) => (
            <button key={s} onClick={() => send(s)} disabled={!!loading} data-suggest={s}
              className="chip hover:border-primary/50 hover:text-foreground text-muted-foreground transition-colors disabled:opacity-50">{s}</button>
          ))}
        </div>
        <button onClick={runCouncil} disabled={!!loading} data-tour="council-btn"
          className="w-full rounded-xl py-2.5 text-sm font-semibold flex items-center justify-center gap-2 text-white bg-gradient-to-r from-primary to-[hsl(270_85%_62%)] hover:opacity-95 disabled:opacity-60 glow-primary transition-opacity">
          <Gavel size={16} /> Convene the council on {activeTicker || '…'}
        </button>
        <div className="flex gap-2">
          <input data-tour="chat-input" className="flex-1 bg-background/60 border border-border/80 rounded-xl px-3.5 py-2 text-sm focus:outline-none focus:border-primary placeholder:text-muted-foreground"
            value={input} onChange={(e) => setInput(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && send()}
            placeholder={activeTicker ? `Ask about ${activeTicker}…` : 'Ask a market question…'} disabled={!!loading} />
          <button onClick={() => send()} disabled={!!loading} className="rounded-xl bg-primary px-3 text-primary-foreground hover:opacity-90 disabled:opacity-50"><Send size={16} /></button>
        </div>
      </div>
    </div>
  );
}
