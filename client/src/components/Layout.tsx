import { useEffect, useRef, useState } from 'react';
import { Outlet, Link, useLocation } from 'react-router-dom';
import { LayoutDashboard, Network, ListPlus, Dumbbell, PanelLeftClose, PanelLeftOpen, TrendingUp, TrendingDown } from 'lucide-react';
import { api } from '@/lib/api';
import { IS_DEMO } from '@/lib/demo';

interface TapeItem { symbol: string; price?: number; change?: number }

const AGENTS = [
  { label: 'Price stream', detail: 'Alpaca · 1-min bars' },
  { label: 'News + risk agent', detail: 'RSS → LLM scoring' },
  { label: 'Supply-chain agent', detail: 'LangGraph' },
  { label: 'Agent council', detail: 'Bull · Bear · Risk' },
];

export const Logo = ({ size = 34 }: { size?: number }) => (
  <div
    className="grid place-items-center rounded-xl text-white shrink-0"
    style={{ width: size, height: size, background: 'linear-gradient(135deg, hsl(248 92% 66%), hsl(190 92% 50%))', boxShadow: '0 8px 24px -8px hsl(248 92% 60% / .7)' }}
  >
    <svg width={size * 0.56} height={size * 0.56} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round">
      <path d="M3 17l5-5 4 4 8-9" />
      <circle cx="20" cy="7" r="1.6" fill="currentColor" />
    </svg>
  </div>
);

const Layout = () => {
  const [open, setOpen] = useState(true);
  const [tape, setTape] = useState<TapeItem[]>([]);
  const location = useLocation();
  const scroller = useRef<HTMLDivElement>(null);
  useEffect(() => { scroller.current?.scrollTo({ top: 0 }); }, [location.pathname]);

  useEffect(() => {
    const load = () => api.getActiveTickers().then((r) => setTape(r.data)).catch(() => {});
    load();
    const id = setInterval(load, 5000);
    return () => clearInterval(id);
  }, []);

  const menu = [
    { icon: LayoutDashboard, label: 'Live Monitor', path: '/' },
    { icon: Network, label: 'Deep Dive', path: '/deepdive' },
    { icon: ListPlus, label: 'Watchlist', path: '/watchlist' },
    { icon: Dumbbell, label: 'Trading Gym', path: '/gym', soon: true },
  ];
  const priced = tape.filter((t) => typeof t.price === 'number');

  return (
    <div className="flex h-screen text-foreground overflow-hidden">
      <aside className={`${open ? 'w-60' : 'w-[72px]'} shrink-0 border-r border-border/70 bg-card/40 backdrop-blur transition-all duration-300 flex flex-col`}>
        <div className="flex items-center gap-3 px-4 h-16">
          <Logo />
          {open && (
            <div className="leading-tight">
              <div className="font-bold tracking-tight">AI Stock Agent</div>
              <div className="text-[11px] text-muted-foreground">Agentic financial analyst</div>
            </div>
          )}
        </div>

        <nav className="flex-1 px-3 py-3 space-y-1">
          {menu.map((item) => {
            const active = location.pathname === item.path;
            return (
              <Link
                key={item.path}
                to={item.path}
                data-nav={item.label}
                className={`flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm transition-all ${
                  active ? 'bg-primary/15 text-foreground ring-1 ring-primary/40' : 'text-muted-foreground hover:bg-secondary hover:text-foreground'
                }`}
              >
                <item.icon className={`w-[18px] h-[18px] ${active ? 'text-primary' : ''}`} />
                {open && <span className="font-medium flex-1">{item.label}</span>}
                {open && item.soon && <span className="text-[10px] rounded-full bg-secondary px-2 py-0.5 text-muted-foreground">Soon</span>}
              </Link>
            );
          })}
        </nav>

        {open && (
          <div className="m-3 rounded-xl border border-border/70 bg-background/40 p-3">
            <div className="text-[11px] uppercase tracking-wider text-muted-foreground mb-2">Background agents</div>
            <div className="space-y-2">
              {AGENTS.map((a, i) => (
                <div key={a.label} className="flex items-center gap-2.5">
                  <span className="relative flex w-2 h-2">
                    <span className="absolute inset-0 rounded-full bg-success animate-ping opacity-60" style={{ animationDelay: `${i * 0.35}s` }} />
                    <span className="relative w-2 h-2 rounded-full bg-success" />
                  </span>
                  <div className="leading-tight">
                    <div className="text-xs font-medium">{a.label}</div>
                    <div className="text-[10px] text-muted-foreground">{a.detail}</div>
                  </div>
                </div>
              ))}
            </div>
            {IS_DEMO && <div className="mt-3 text-[10px] text-warning/90">Demo mode · simulated prices</div>}
          </div>
        )}

        <button onClick={() => setOpen(!open)} className="m-3 mt-0 p-2 rounded-lg text-muted-foreground hover:bg-secondary hover:text-foreground self-start">
          {open ? <PanelLeftClose size={18} /> : <PanelLeftOpen size={18} />}
        </button>
      </aside>

      <main className="flex-1 flex flex-col min-w-0">
        {priced.length > 0 && (
          <div className="h-10 shrink-0 border-b border-border/70 bg-card/30 overflow-hidden flex items-center">
            <div className="flex marquee whitespace-nowrap">
              {[...priced, ...priced, ...priced, ...priced].map((t, i) => (
                <div key={i} className="flex items-center gap-2 px-5 text-xs font-mono">
                  <span className="font-bold text-foreground">{t.symbol}</span>
                  <span className="text-muted-foreground">${t.price!.toFixed(2)}</span>
                  <span className={`flex items-center gap-0.5 ${t.change! >= 0 ? 'text-success' : 'text-destructive'}`}>
                    {t.change! >= 0 ? <TrendingUp size={12} /> : <TrendingDown size={12} />}
                    {t.change! >= 0 ? '+' : ''}{t.change!.toFixed(2)}%
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}
        <div ref={scroller} className="flex-1 overflow-auto">
          <div className="max-w-[1600px] mx-auto p-5">
            <Outlet />
          </div>
        </div>
      </main>
    </div>
  );
};

export default Layout;
