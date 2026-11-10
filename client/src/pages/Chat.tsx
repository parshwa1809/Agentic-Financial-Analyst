import { useState, useEffect, useRef } from 'react';
import { Send, Sparkles, LineChart, Landmark, Scale, Network, Newspaper, Check, ExternalLink, AlertTriangle, BookOpen } from 'lucide-react';
import { api } from '@/lib/api';
import PlainText from '@/components/PlainText';

interface Verdict {
  verdict?: string; decision?: string; confidence?: number; rating?: string | null;
  horizon?: string; time_horizon?: string; analysis?: string; reasoning?: string;
  bull_case?: string; bear_case?: string;
  sources?: Array<{ id: string; title: string; url?: string | null; doc_type: string }>;
  unsupported_numbers?: string[]; model?: string | null; created_at?: string;
  weighted_score?: number;
  agents?: Array<{ agent: string; label: string; prefix?: string; summary: string; key_points: string[]; gaps?: string[] | string; facts: string[]; unsupported_numbers: string[] }>;
}

const AgentRow = ({ a }: { a: NonNullable<Verdict['agents']>[number] }) => {
  const [open, setOpen] = useState(false);
  return (
    <div className="rounded-lg border border-border/60 bg-background/40 px-2.5 py-2 text-[11.5px]">
      <button onClick={() => setOpen(!open)} className="w-full flex items-center gap-2 text-left">
        <span className="font-semibold flex-1">{a.label}</span>
        <span className="text-[10px] text-muted-foreground">{open ? 'hide' : 'details'}</span>
      </button>
      <div className="text-muted-foreground mt-1 leading-snug"><PlainText text={a.summary} /></div>
      {open && (
        <div className="mt-1.5 space-y-1">
          {a.key_points.length > 0 && <PlainText text={a.key_points.map((k) => `- ${k}`).join('\n')} />}
          {a.gaps && a.gaps.length > 0 && <div className="text-[10.5px] text-muted-foreground">Not in the data: {Array.isArray(a.gaps) ? a.gaps.join('; ') : a.gaps}</div>}
          <div className="text-[10px] uppercase tracking-wider text-muted-foreground mt-1.5">All facts used, with their ids</div>
          {a.facts.map((f, i) => <div key={i} className="text-[10.5px] text-muted-foreground leading-snug"><span className="font-mono text-primary/80">{a.prefix || 'F'}{i + 1}</span> {f}</div>)}
          {a.unsupported_numbers.length > 0 && <div className="text-warning text-[10.5px]">Not found in its facts: {a.unsupported_numbers.join(', ')}</div>}
        </div>
      )}
    </div>
  );
};
interface Source { id: string; title: string; doc_type: string; url?: string | null; published_at?: string | null; score: number; cited: boolean; snippet: string }
type Message =
  | { role: 'user' | 'bot'; content: string; sources?: Source[]; unsupported?: string[]; indexing?: boolean; mode?: string; model?: string | null; cached?: boolean }
  | { role: 'council'; ticker: string; result: Verdict };

const DOC_CLS: Record<string, string> = {
  filing: 'bg-success/15 text-success', data: 'bg-success/15 text-success', news: 'bg-info/15 text-info', profile: 'bg-primary/15 text-primary', relationship: 'bg-warning/15 text-warning',
};

/** Sources the answer was built from, cited ones first, plus the number check. */
const SourceList = ({ m }: { m: Extract<Message, { role: 'user' | 'bot' }> }) => {
  const [open, setOpen] = useState(false);
  const srcs = [...(m.sources || [])].sort((a, b) => Number(b.cited) - Number(a.cited));
  if (!srcs.length && !m.unsupported?.length && !m.indexing) return null;
  const shown = open ? srcs : srcs.filter((s) => s.cited).slice(0, 4);
  return (
    <div className="mt-1.5 space-y-1.5 max-w-[88%]">
      {m.unsupported && m.unsupported.length > 0 && (
        <div className="flex gap-1.5 items-start rounded-lg bg-warning/10 text-warning px-2.5 py-1.5 text-[11px]">
          <AlertTriangle size={13} className="shrink-0 mt-0.5" />
          <span>Not found in the sources, so treat with care: <b className="font-mono">{m.unsupported.join(', ')}</b></span>
        </div>
      )}
      {m.indexing && <div className="text-[11px] text-info">Indexing this company's filings and news now — ask again in a minute for sourced answers.</div>}
      {shown.map((s) => (
        <div key={s.id} className="rounded-lg border border-border/60 bg-background/40 px-2.5 py-1.5 text-[11px]">
          <div className="flex items-center gap-1.5">
            <span className="font-mono font-bold text-primary">[{s.id}]</span>
            <span className={`rounded-full px-1.5 py-0.5 text-[10px] font-semibold ${DOC_CLS[s.doc_type] || 'bg-secondary'}`}>{s.doc_type}</span>
            <span className="truncate flex-1" title={s.title}>{s.title}</span>
            {s.url && <a href={s.url} target="_blank" rel="noreferrer" className="text-info hover:text-foreground" aria-label="Open source"><ExternalLink size={11} /></a>}
          </div>
          <div className="text-muted-foreground mt-0.5 line-clamp-2">{s.snippet}</div>
        </div>
      ))}
      {srcs.length > shown.length || open ? (
        <button onClick={() => setOpen(!open)} className="text-[11px] text-muted-foreground hover:text-foreground flex items-center gap-1">
          <BookOpen size={12} /> {open ? 'Show cited sources only' : `Show all ${srcs.length} retrieved sources`}
        </button>
      ) : null}
    </div>
  );
};

interface ChatProps { isEmbedded?: boolean; activeTicker?: string | null }

const SUGGESTIONS = ['Is it a buy, hold or sell?', 'What were its revenue and profit last year?', 'Revenue and net income over the past years', 'How volatile is it compared with the market?', 'Who are its suppliers and customers?', 'What risks does its annual report (10-K) mention?', 'Latest news'];

const AGENTS = [
  { icon: Scale, name: 'Fair value & rating', task: 'three valuation methods and the buy / hold / sell rule…' },
  { icon: Landmark, name: 'Money in and out', task: 'revenue, profit, cash and debt from the SEC reports…' },
  { icon: LineChart, name: 'Share price', task: 'how the price moved and swung vs the overall market…' },
  { icon: Network, name: 'Suppliers, customers & competitors', task: 'companies named in filings and articles…' },
  { icon: Newspaper, name: 'News & SEC filings', task: 'recent headlines and official reports…' },
];

const BriefingCard = ({ ticker, r }: { ticker: string; r: Verdict }) => {
  return (
    <div className="fade-up rounded-2xl border border-border/80 bg-background/60 overflow-hidden" data-tour="verdict">
      <div className="px-3.5 py-3 border-b border-border/70">
        <div className="flex items-center gap-2 text-[10px] uppercase tracking-wider text-muted-foreground">Briefing · {ticker}
          {r.rating && <span className={`rounded-full px-2 py-0.5 font-bold normal-case tracking-normal ${r.rating === 'BUY' ? 'bg-success/15 text-success' : r.rating === 'SELL' ? 'bg-destructive/15 text-destructive' : 'bg-warning/15 text-warning'}`} title="From Oracle's fixed formula (fair value ±10%), not an AI opinion">Formula rating: {r.rating}</span>}
        </div>
        <div className="text-[11px] text-muted-foreground mt-0.5">Built from the company's SEC reports, share prices and saved sources, with no AI. The small letters (A1, M2…) show where each sentence comes from. The rating comes from a fixed formula, not from AI, and is not personal advice.</div>
      </div>
      <div className="px-3.5 py-3 text-[12.5px] leading-relaxed text-foreground/90"><PlainText text={r.analysis || r.reasoning || ''} sources={r.sources} /></div>
      {r.agents && r.agents.length > 0 && (
        <div className="px-3.5 pb-3 space-y-1.5">
          <div className="flex justify-between text-[10px] uppercase tracking-wider text-muted-foreground">
            <span>Each topic · tap “details” for every fact and its id</span>
          </div>
          {r.agents.map((a) => <AgentRow key={a.agent} a={a} />)}
        </div>
      )}
      {r.unsupported_numbers && r.unsupported_numbers.length > 0 && (
        <div className="mx-3.5 mb-2 flex gap-1.5 items-start rounded-lg bg-warning/10 text-warning px-2.5 py-1.5 text-[11px]">
          <AlertTriangle size={13} className="shrink-0 mt-0.5" /><span>Not found in the sources: <b className="font-mono">{r.unsupported_numbers.join(', ')}</b></span>
        </div>
      )}
      {r.sources && r.sources.length > 0 && (
        <div className="px-3.5 pb-3 flex flex-wrap gap-1.5">
          {r.sources.map((s) => (
            <a key={s.id} href={s.url || undefined} target="_blank" rel="noreferrer" title={s.title}
              className="chip text-[10.5px] max-w-[220px] truncate hover:text-foreground text-muted-foreground"><b className="font-mono text-primary">[{s.id}]</b> {s.title}</a>
          ))}
        </div>
      )}
      {(r.model || r.created_at) && <div className="px-3.5 pb-2.5 text-[10px] text-muted-foreground">{[r.model, r.created_at && `generated ${r.created_at}`].filter(Boolean).join(' · ')}</div>}
    </div>
  );
};

export default function Chat({ isEmbedded = false, activeTicker: propTicker }: ChatProps) {
  const [messages, setMessages] = useState<Message[]>([
    { role: 'bot', content: 'Hi! I read live prices, indicators, news and supply-chain data for your watchlist. Ask me anything, or get a sourced briefing on the selected company.' },
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
      setMessages((p) => [...p, { role: 'bot', content: res.data.response, sources: res.data.sources, unsupported: res.data.unsupported_numbers, indexing: res.data.indexing, mode: res.data.mode, model: res.data.model, cached: res.data.cached }]);
    } catch {
      setMessages((p) => [...p, { role: 'bot', content: 'Error connecting to the AI brain.' }]);
    } finally { setLoading(false); }
  };

  const runCouncil = async (refresh = false) => {
    if (!activeTicker || loading) return;
    setMessages((p) => [...p, { role: 'user', content: refresh ? `Fresh briefing on ${activeTicker}` : `Brief me on ${activeTicker}` }]);
    setLoading('council');
    try {
      const res = await api.runCouncil(activeTicker, refresh);
      const result = res.data.result;
      setMessages((p) => [...p, result ? { role: 'council', ticker: activeTicker, result } : { role: 'bot', content: '⚠️ Could not read the briefing.' }]);
    } catch {
      setMessages((p) => [...p, { role: 'bot', content: 'The briefing service is offline right now.' }]);
    } finally { setLoading(false); }
  };

  return (
    <div className={`panel flex flex-col overflow-hidden ${isEmbedded ? 'h-full' : 'h-[640px] max-w-3xl mx-auto'}`}>
      <div className="flex items-center gap-3 px-4 py-3.5 border-b border-border/70">
        <div className="grid place-items-center w-9 h-9 rounded-xl bg-gradient-to-br from-primary to-info text-white"><Sparkles size={18} /></div>
        <div className="leading-tight flex-1">
          <div className="font-semibold">AI Analyst</div>
          <div className="text-[11px] text-muted-foreground">Answers in plain words · every number linked to its source · rating by formula, not AI opinion</div>
        </div>
        {activeTicker && <span className="chip font-mono font-bold">{activeTicker}</span>}
      </div>

      <div ref={scrollRef} className="flex-1 overflow-y-auto scroll-panel p-4 space-y-3 min-h-0" data-tour="chat">
        {messages.map((m, i) =>
          m.role === 'council' ? (
            <BriefingCard key={i} ticker={m.ticker} r={m.result} />
          ) : (
            <div key={i} className={`fade-up flex flex-col ${m.role === 'user' ? 'items-end' : 'items-start'}`}>
              <div className={`max-w-[88%] rounded-2xl px-3.5 py-2.5 text-[13px] leading-relaxed ${
                m.role === 'user' ? 'bg-primary text-primary-foreground rounded-br-md whitespace-pre-wrap' : 'bg-secondary/80 border border-border/60 rounded-bl-md'}`}>
                {m.role === 'user' ? m.content : <PlainText text={m.content} sources={m.sources} />}
              </div>
              {m.role === 'bot' && m.mode && (
                <div className="text-[10px] text-muted-foreground mt-1">
                  {m.mode === 'facts' ? 'Built straight from SEC filings, prices and saved sources · no AI used' : m.mode === 'ai' ? `Written by AI from the sources below · ${m.model || ''}${m.cached ? ' · saved answer' : ''}` : ''}
                  {' · dotted words: hover for a definition · small letters like A1 link to the source'}
                </div>
              )}
              {m.role === 'bot' && <SourceList m={m} />}
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
            <div className="text-[10px] uppercase tracking-wider text-muted-foreground">Putting the briefing together</div>
            {AGENTS.map((a, i) => {
              const done = step > i, live = step === i;
              return (
                <div key={a.name} className={`flex items-center gap-2.5 transition-opacity ${step >= i ? 'opacity-100' : 'opacity-35'}`}>
                  <span className={`grid place-items-center w-7 h-7 rounded-lg ${done ? 'bg-success/15 text-success' : 'bg-primary/15 text-primary'}`}>
                    {done ? <Check size={14} /> : <a.icon size={14} className={live ? 'animate-pulse' : ''} />}
                  </span>
                  <div className="leading-tight text-[12px]">
                    <div className="font-semibold">{a.name}</div>
                    <div className="text-muted-foreground">{done ? 'done' : a.task}</div>
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
        <button onClick={() => runCouncil()} disabled={!!loading} data-tour="council-btn"
          className="w-full rounded-xl py-2.5 text-sm font-semibold flex items-center justify-center gap-2 text-white bg-gradient-to-r from-primary to-[hsl(270_85%_62%)] hover:opacity-95 disabled:opacity-60 glow-primary transition-opacity">
          <BookOpen size={16} /> Brief me on {activeTicker || '…'}
        </button>
        <button onClick={() => runCouncil(true)} disabled={!!loading} className="w-full text-[11px] text-muted-foreground hover:text-foreground disabled:opacity-50">
          Shows the latest briefing · rebuild it from today's data (no AI call)
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
