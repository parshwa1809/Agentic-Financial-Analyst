import { useState, useEffect, useRef } from 'react';
import { Send, Bot, User, Loader2, Gavel } from 'lucide-react';
import { api } from '@/lib/api';

interface Message {
  role: 'user' | 'bot';
  content: string;
}

interface ChatProps {
  isEmbedded?: boolean;
  activeTicker?: string | null;
}

export default function Chat({ isEmbedded = false, activeTicker: propTicker }: ChatProps) {
  const [messages, setMessages] = useState<Message[]>([
    { role: 'bot', content: 'Hello. I am your financial analyst. What would you like to know?' }
  ]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [activeTicker, setActiveTicker] = useState<string | null>(propTicker || null);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (propTicker && propTicker !== activeTicker) {
      setActiveTicker(propTicker);
    } else if (!propTicker && !activeTicker) {
       api.getActiveTickers().then(res => {
        if (res.data.length > 0) setActiveTicker(res.data[0].symbol);
      }).catch(() => {});
    }
  }, [propTicker, activeTicker]);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages]);

  const handleSend = async () => {
    if (!input.trim()) return;
    
    const userText = input;
    setMessages(prev => [...prev, { role: 'user', content: userText }]);
    setInput('');
    setLoading(true);

    try {
      const res = await api.chat(userText, activeTicker || undefined);
      setMessages(prev => [...prev, { role: 'bot', content: res.data.response }]);
    } catch (e) {
      setMessages(prev => [...prev, { role: 'bot', content: "Error connecting to AI brain." }]);
    } finally {
      setLoading(false);
    }
  };

  const handleCouncil = async () => {
    if (!activeTicker) {
      setMessages(prev => [...prev, { role: 'bot', content: "Please select a ticker to debate first." }]);
      return;
    }
    
    setMessages(prev => [...prev, { role: 'user', content: `Run Council Debate for ${activeTicker}` }]);
    setLoading(true);
    
    try {
      const res = await api.runCouncil(activeTicker);
      // --- CRITICAL FIX: Unwrap JSON object to String ---
      const result = res.data.result;
      
      let formatted = "⚠️ Error parsing verdict.";
      if (result) {
        formatted = `🏛️ **COUNCIL VERDICT: ${result.decision}**\n` + 
                    `Confidence: ${(result.confidence * 100).toFixed(0)}%\n` +
                    `Horizon: ${result.time_horizon}\n\n` + 
                    `${result.reasoning}`;
      }
      
      setMessages(prev => [...prev, { role: 'bot', content: formatted }]);
    } catch {
      setMessages(prev => [...prev, { role: 'bot', content: "Council is currently offline or errored." }]);
    } finally {
      setLoading(false);
    }
  };

  const containerClass = isEmbedded 
    ? "flex flex-col h-full min-h-0 bg-card overflow-hidden" 
    : "flex flex-col h-[600px] w-full max-w-4xl mx-auto bg-card rounded-xl border border-border overflow-hidden";

  return (
    <div className={containerClass}>
      <div ref={scrollRef} className="flex-1 overflow-y-auto p-4 space-y-4 min-h-0 w-full">
        {messages.map((m, i) => (
          <div key={i} className={`flex gap-3 ${m.role === 'user' ? 'flex-row-reverse' : ''}`}>
            <div className={`w-8 h-8 rounded-full flex items-center justify-center flex-shrink-0 ${m.role === 'bot' ? 'bg-primary text-primary-foreground' : 'bg-muted'}`}>
              {m.role === 'bot' ? <Bot size={18} /> : <User size={18} />}
            </div>
            <div className={`p-3 rounded-lg max-w-[85%] text-sm break-words whitespace-pre-wrap ${m.role === 'bot' ? 'bg-muted text-foreground' : 'bg-primary text-primary-foreground'}`}>
              {m.content}
            </div>
          </div>
        ))}
        {loading && (
          <div className="flex gap-3"><div className="w-8 h-8 rounded-full bg-primary text-primary-foreground flex items-center justify-center"><Bot size={18} /></div><div className="bg-muted p-3 rounded-lg"><Loader2 className="animate-spin" size={18} /></div></div>
        )}
      </div>

      <div className="p-4 bg-background/80 border-t border-border shrink-0">
        <button onClick={handleCouncil} disabled={loading} className="mb-3 w-full bg-[hsl(var(--warning))] hover:opacity-90 text-background p-2 rounded-lg flex items-center justify-center gap-2 transition-opacity font-medium text-xs uppercase tracking-wide disabled:opacity-50">
          <Gavel size={16} /> Run Council Debate for {activeTicker || 'Ticker'}
        </button>
        <div className="flex gap-2">
          <input className="flex-1 bg-muted border border-border rounded-lg px-4 py-2 text-foreground focus:outline-none focus:border-primary placeholder:text-muted-foreground text-sm" value={input} onChange={(e) => setInput(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && handleSend()} placeholder={activeTicker ? `Ask about ${activeTicker}...` : "Ask a market question..."} disabled={loading} />
          <button onClick={handleSend} disabled={loading} className="bg-primary hover:opacity-90 text-primary-foreground p-2 rounded-lg transition-opacity disabled:opacity-50"><Send size={18} /></button>
        </div>
      </div>
    </div>
  );
}