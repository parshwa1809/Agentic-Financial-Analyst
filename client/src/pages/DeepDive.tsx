import { useState, useEffect, useMemo } from 'react';
import { api } from '@/lib/api';
import { Network, ArrowDownToLine, ArrowUpFromLine, Swords, Newspaper, LineChart, Link2, GitFork, Layers } from 'lucide-react';

interface Ticker { symbol: string; name: string }
interface ChainNode { id: string; type: string; depth?: number; change?: number }
interface ChainLink { source?: string; target: string; type: string; depth?: number }
interface Chain { nodes: ChainNode[]; links: ChainLink[] }
interface Placed { id: string; type: string; depth: number; x: number; y: number; angle: number; change?: number }

const COLORS: Record<string, string> = {
  SUPPLIER: 'hsl(152 70% 46%)',
  CUSTOMER: 'hsl(190 92% 55%)',
  COMPETITOR: 'hsl(38 96% 58%)',
};
const colorOf = (t: string) => COLORS[t] || COLORS.SUPPLIER;

const W = 1000, H = 640, CX = W / 2, CY = 320;
const deg = Math.PI / 180;
const R1 = { x: 255, y: 185 }, R2 = { x: 440, y: 290 };

// ---------------------------------------------------------------- layout
function layoutGraph(center: string, chain: Chain) {
  const changeOf = (id: string) => chain.nodes.find((n) => n.id === id)?.change;
  const first = chain.links.filter((l) => (l.depth ?? 1) === 1 && (l.source ?? center) === center);
  const second = chain.links.filter((l) => (l.depth ?? 1) === 2);
  const r1 = second.length ? R1 : { x: 330, y: 230 };
  const placed = new Map<string, Placed>();
  placed.set(center, { id: center, type: 'TARGET', depth: 0, x: CX, y: CY, angle: 0, change: changeOf(center) });

  // Direct partners share the inner ring: customers on the right, competitors
  // at the bottom, suppliers on the left, with a gap between groups.
  const order = ['CUSTOMER', 'COMPETITOR', 'SUPPLIER'];
  const firstUnique = first.filter((l, i, self) => self.findIndex((x) => x.target === l.target) === i);
  const grouped = order.map((t) => firstUnique.filter((l) => (COLORS[l.type] ? l.type : 'SUPPLIER') === t));
  const slots = firstUnique.length + order.length;
  const step = 360 / Math.max(slots, 8);
  let a = -60;
  grouped.forEach((list) => {
    list.forEach((l) => {
      const ang = a * deg;
      placed.set(l.target, { id: l.target, type: l.type, depth: 1, angle: ang, x: CX + r1.x * Math.cos(ang), y: CY + r1.y * Math.sin(ang), change: changeOf(l.target) });
      a += step;
    });
    a += step;
  });

  // Second-order companies fan out behind the partner that links to them
  const kids = new Map<string, string[]>();
  second.forEach((l) => {
    if (placed.has(l.target) || l.target === center) return;
    const list = kids.get(l.source!) || [];
    if (!list.includes(l.target) && ![...kids.values()].some((k) => k.includes(l.target))) kids.set(l.source!, [...list, l.target]);
  });
  kids.forEach((list, parent) => {
    const p = placed.get(parent);
    if (!p) return;
    list.forEach((id, k) => {
      const ang = p.angle + (k - (list.length - 1) / 2) * 15 * deg;
      const type = second.find((l) => l.target === id)!.type;
      placed.set(id, { id, type, depth: 2, angle: ang, x: CX + R2.x * Math.cos(ang), y: CY + R2.y * Math.sin(ang), change: changeOf(id) });
    });
  });

  // Light collision pass so labels never sit on top of each other
  const pts = [...placed.values()].filter((n) => n.depth > 0);
  for (let it = 0; it < 80; it++) {
    for (let i = 0; i < pts.length; i++) for (let j = i + 1; j < pts.length; j++) {
      const A = pts[i], B = pts[j];
      const min = (A.depth === 2 ? 30 : 38) + (B.depth === 2 ? 30 : 38) + 8;
      const dx = B.x - A.x, dy = B.y - A.y, d = Math.hypot(dx, dy) || 1;
      if (d < min) {
        const push = (min - d) / 2, ux = dx / d, uy = dy / d;
        const wa = A.depth === 1 ? 0.35 : 1, wb = B.depth === 1 ? 0.35 : 1;
        A.x -= ux * push * wa; A.y -= uy * push * wa; B.x += ux * push * wb; B.y += uy * push * wb;
      }
    }
    pts.forEach((n) => { n.x = Math.max(36, Math.min(W - 36, n.x)); n.y = Math.max(36, Math.min(H - 36, n.y)); });
  }

  const edges = [
    ...firstUnique.map((l) => ({ from: center, to: l.target, type: l.type, depth: 1 })),
    ...second.filter((l) => placed.has(l.source!) && placed.has(l.target) && l.target !== center)
      .map((l) => ({ from: l.source!, to: l.target, type: l.type, depth: 2 })),
  ];
  return { nodes: [...placed.values()], edges, r1 };
}

// ---------------------------------------------------------------- insights
interface Path { kind: 'upstream' | 'shared' | 'downstream'; chain: string[]; move?: number; text: string }

function secondOrderPaths(center: string, chain: Chain): Path[] {
  const changeOf = (id: string) => chain.nodes.find((n) => n.id === id)?.change;
  const first = chain.links.filter((l) => (l.depth ?? 1) === 1);
  const typeOf = (id: string) => first.find((l) => l.target === id)?.type;
  const out: Path[] = [];
  chain.links.filter((l) => l.depth === 2 && l.target !== center).forEach((l) => {
    const via = l.source!, rel = typeOf(via);
    if (rel === 'SUPPLIER' && l.type === 'SUPPLIER') {
      out.push({ kind: 'upstream', chain: [l.target, via, center], move: changeOf(l.target), text: `${l.target} supplies ${via}, which supplies ${center}` });
    } else if (rel === 'SUPPLIER' && l.type === 'CUSTOMER' && typeOf(l.target) === 'COMPETITOR') {
      out.push({ kind: 'shared', chain: [via, l.target], text: `${via} also supplies rival ${l.target}, so capacity is contested` });
    } else if (rel === 'CUSTOMER' && l.type === 'CUSTOMER') {
      out.push({ kind: 'downstream', chain: [center, via, l.target], move: changeOf(l.target), text: `${l.target}'s demand flows through ${via} to ${center}` });
    }
  });
  const rank = { upstream: 0, shared: 1, downstream: 2 };
  return out.sort((a, b) => rank[a.kind] - rank[b.kind] || (a.move ?? 0) - (b.move ?? 0)).slice(0, 7);
}

const Move = ({ v }: { v?: number }) =>
  v === undefined ? null : <span className={`font-mono text-[11px] ${v >= 0 ? 'text-success' : 'text-destructive'}`}>{v >= 0 ? '+' : ''}{v.toFixed(1)}%</span>;

// ---------------------------------------------------------------- graph
const NetworkMap = ({ center, chain, highlight }: { center: string; chain: Chain; highlight: string[] | null }) => {
  const { nodes, edges, r1 } = useMemo(() => layoutGraph(center, chain), [center, chain]);
  const [hover, setHover] = useState<string | null>(null);
  const on = (id: string) => (highlight ? highlight.includes(id) : !hover || hover === id || id === center);
  const edgeOn = (a: string, b: string) => {
    if (highlight) {
      const i = highlight.indexOf(a), j = highlight.indexOf(b);
      return i >= 0 && j >= 0 && Math.abs(i - j) === 1;
    }
    return !hover || hover === a || hover === b;
  };

  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full h-auto select-none" data-tour="network">
      <defs>
        <radialGradient id="core" cx="50%" cy="40%" r="60%">
          <stop offset="0%" stopColor="hsl(248 92% 76%)" />
          <stop offset="100%" stopColor="hsl(248 80% 50%)" />
        </radialGradient>
        <filter id="glow"><feGaussianBlur stdDeviation="9" /></filter>
      </defs>
      <ellipse cx={CX} cy={CY} rx={r1.x} ry={r1.y} fill="none" stroke="hsl(var(--border))" strokeDasharray="2 7" />
      {nodes.some((n) => n.depth === 2) && <ellipse cx={CX} cy={CY} rx={R2.x} ry={R2.y} fill="none" stroke="hsl(var(--border))" strokeDasharray="2 7" opacity={0.6} />}

      {edges.map((e, i) => {
        const a = nodes.find((n) => n.id === e.from)!, b = nodes.find((n) => n.id === e.to)!;
        const lit = edgeOn(e.from, e.to);
        const hot = !!highlight && lit;
        // supply flows toward the buyer: supplier -> buyer
        const [p, q] = e.type === 'SUPPLIER' ? [b, a] : [a, b];
        return (
          <line key={`${e.from}-${e.to}-${i}`} x1={p.x} y1={p.y} x2={q.x} y2={q.y}
            stroke={hot ? 'hsl(350 89% 64%)' : colorOf(e.type)} strokeWidth={hot ? 3.2 : e.depth === 2 ? 1.2 : 2}
            className={e.type === 'COMPETITOR' ? '' : 'flow'} strokeDasharray={e.type === 'COMPETITOR' ? '3 6' : undefined}
            opacity={lit ? (e.depth === 2 && !hot ? 0.55 : 0.85) : 0.08}
            style={{ transition: 'opacity .3s, stroke .3s' }} />
        );
      })}

      <circle cx={CX} cy={CY} r={66} fill="hsl(248 92% 68%)" opacity={0.35} filter="url(#glow)" />
      <circle cx={CX} cy={CY} r={54} fill="url(#core)" />
      <text x={CX} y={CY + 7} textAnchor="middle" fontSize="24" fontWeight="800" fill="#fff" className="font-mono">{center}</text>

      {nodes.filter((n) => n.depth > 0).map((n, i) => {
        const c = colorOf(n.type), r = n.depth === 2 ? 28 : 36;
        const hot = !!highlight && highlight.includes(n.id);
        return (
          <g key={n.id} onMouseEnter={() => setHover(n.id)} onMouseLeave={() => setHover(null)}
            style={{ cursor: 'pointer', opacity: on(n.id) ? 1 : 0.22, transition: 'opacity .3s' }}>
            <g className="fade-up" style={{ animationDelay: `${(n.depth === 2 ? 0.35 : 0.1) + i * 0.05}s` }}>
              {hot && <circle cx={n.x} cy={n.y} r={r + 9} fill="hsl(350 89% 62%)" opacity={0.35} filter="url(#glow)" />}
              <circle cx={n.x} cy={n.y} r={r} fill="hsl(var(--card))" stroke={hot ? 'hsl(350 89% 64%)' : c} strokeWidth={n.depth === 2 ? 1.5 : 2.2}
                strokeDasharray={n.depth === 2 ? '4 3' : undefined} />
              <text x={n.x} y={n.y + (n.change !== undefined ? 1 : 4.5)} textAnchor="middle" fontSize={n.depth === 2 ? 13 : 15} fontWeight="700" fill="currentColor" className="font-mono">{n.id}</text>
              {n.change !== undefined && (
                <text x={n.x} y={n.y + 16} textAnchor="middle" fontSize="11.5" className="font-mono"
                  fill={n.change >= 0 ? 'hsl(152 70% 50%)' : 'hsl(350 89% 66%)'}>{n.change >= 0 ? '+' : ''}{n.change.toFixed(1)}%</text>
              )}
            </g>
          </g>
        );
      })}
    </svg>
  );
};

// ---------------------------------------------------------------- page
export default function DeepDive() {
  const [ticker, setTicker] = useState('');
  const [available, setAvailable] = useState<Ticker[]>([]);
  const [chain, setChain] = useState<Chain>({ nodes: [], links: [] });
  const [depth, setDepth] = useState(1);
  const [risk, setRisk] = useState(0);
  const [loading, setLoading] = useState(false);
  const [highlight, setHighlight] = useState<string[] | null>(null);

  const load = async (sym: string, d = depth) => {
    if (!sym) return;
    setTicker(sym); setLoading(true); setHighlight(null);
    try {
      const [res, stats] = await Promise.all([api.getSupplyChain(sym, d), api.getStats(sym)]);
      setChain(res.data);
      setRisk(stats.data.risk_score || 0);
    } catch (e) { console.error(e); }
    setLoading(false);
  };

  useEffect(() => {
    api.getActiveTickers().then((res) => {
      setAvailable(res.data);
      if (res.data.length) load(res.data[0].symbol);
    }).catch(() => {});
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const switchDepth = (d: number) => { setDepth(d); load(ticker, d); };

  const firstOrder = chain.links.filter((l) => (l.depth ?? 1) === 1);
  const by = (t: string) => firstOrder.filter((l) => l.type === t);
  const paths = useMemo(() => secondOrderPaths(ticker, chain), [ticker, chain]);
  const secondCount = new Set(chain.nodes.filter((n) => n.depth === 2).map((n) => n.id)).size;
  const riskColor = risk > 65 ? 'hsl(350 89% 62%)' : risk > 45 ? 'hsl(38 96% 58%)' : 'hsl(152 70% 46%)';

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <div className="flex items-center gap-2 text-2xl font-bold tracking-tight"><Network className="text-primary" /> Deep Dive</div>
          <p className="text-sm text-muted-foreground mt-1">The supply-chain map the LLM agent built, and how risk travels through it.</p>
        </div>
        <div className="flex gap-2 flex-wrap">
          {available.map((t) => (
            <button key={t.symbol} data-ticker={t.symbol} onClick={() => load(t.symbol)}
              className={`rounded-xl px-3.5 py-2 text-sm font-bold border transition-all ${t.symbol === ticker ? 'bg-primary/15 border-primary/50 glow-primary' : 'bg-card/70 border-border/70 hover:border-primary/40'}`}>{t.symbol}</button>
          ))}
        </div>
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-[minmax(0,1fr)_330px] gap-5">
        <div className="panel p-4">
          <div className="flex flex-wrap items-center justify-between gap-3 mb-1">
            <div className="flex items-center gap-1 rounded-xl bg-background/60 border border-border/70 p-1" data-tour="depth">
              {[1, 2].map((d) => (
                <button key={d} data-depth={d} onClick={() => switchDepth(d)}
                  className={`flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold rounded-lg transition-colors ${depth === d ? 'bg-primary text-primary-foreground' : 'text-muted-foreground hover:text-foreground'}`}>
                  {d === 1 ? <GitFork size={13} /> : <Layers size={13} />}{d === 1 ? '1st-order' : '2nd-order'}
                </button>
              ))}
            </div>
            <div className="flex gap-3 text-[11px] text-muted-foreground">
              {Object.entries(COLORS).map(([k, c]) => <span key={k} className="flex items-center gap-1.5"><span className="w-2 h-2 rounded-full" style={{ background: c }} />{k.toLowerCase()}s</span>)}
              {depth === 2 && <span className="flex items-center gap-1.5"><span className="w-2.5 h-2.5 rounded-full border border-dashed border-muted-foreground" />2nd-order</span>}
            </div>
          </div>
          {loading && chain.links.length === 0 ? (
            <div className="h-[480px] grid place-items-center text-muted-foreground text-sm">Mapping supply chain…</div>
          ) : chain.links.length === 0 ? (
            <div className="h-[480px] grid place-items-center text-muted-foreground text-sm">No relationships discovered yet. The agent is still researching.</div>
          ) : (
            <NetworkMap key={`${ticker}-${depth}`} center={ticker} chain={chain} highlight={highlight} />
          )}
          <div className="flex gap-5 px-1 text-xs text-muted-foreground">
            <span><b className="text-foreground font-mono">{firstOrder.length}</b> direct partners</span>
            {depth === 2 && <span><b className="text-foreground font-mono">{secondCount}</b> second-order companies</span>}
          </div>
        </div>

        <div className="space-y-5">
          {depth === 2 ? (
            <div className="panel p-4 fade-up" data-tour="paths">
              <div className="flex items-center gap-2 font-semibold"><Layers size={16} className="text-primary" /> Second-order exposure</div>
              <p className="text-[11px] text-muted-foreground mt-1">Risk your watchlist inherits from partners of partners. Hover a path to trace it.</p>
              <div className="mt-3 space-y-2">
                {paths.map((p, i) => (
                  <div key={i} data-path={i} onMouseEnter={() => setHighlight(p.chain)} onMouseLeave={() => setHighlight(null)}
                    className={`rounded-xl border p-2.5 cursor-default transition-colors ${highlight === p.chain ? 'border-destructive/60 bg-destructive/10' : 'border-border/60 bg-background/40'}`}>
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-1 font-mono text-xs font-bold">
                        {p.chain.map((c, j) => <span key={j} className="flex items-center gap-1">{j > 0 && <span className="text-muted-foreground">→</span>}{c}</span>)}
                      </div>
                      {p.kind === 'shared' ? <span className="text-[10px] rounded-full bg-warning/15 text-warning px-2 py-0.5">shared supplier</span> : <Move v={p.move} />}
                    </div>
                    <div className="text-[11px] text-muted-foreground mt-1">{p.text}</div>
                  </div>
                ))}
                {paths.length === 0 && <div className="text-xs text-muted-foreground italic">No second-order paths found yet.</div>}
              </div>
            </div>
          ) : (
            <div className="panel p-4 space-y-4">
              {[
                { type: 'SUPPLIER', title: 'Suppliers', icon: ArrowDownToLine, verb: 'supplies' },
                { type: 'CUSTOMER', title: 'Customers', icon: ArrowUpFromLine, verb: 'buys' },
                { type: 'COMPETITOR', title: 'Competitors', icon: Swords, verb: 'rival' },
              ].map(({ type, title, icon: Icon, verb }) => (
                <div key={type}>
                  <div className="flex items-center gap-2 text-xs font-semibold mb-2" style={{ color: COLORS[type] }}><Icon size={14} /> {title} <span className="text-muted-foreground font-normal">({by(type).length})</span></div>
                  <div className="space-y-1.5">
                    {by(type).map((l) => (
                      <div key={l.target} className="flex items-center justify-between rounded-lg bg-background/50 border border-border/60 px-2.5 py-1.5 text-xs">
                        <span className="font-mono font-bold">{l.target}</span>
                        <span className="flex items-center gap-2"><Move v={chain.nodes.find((n) => n.id === l.target)?.change} /><span className="text-muted-foreground">{verb}</span></span>
                      </div>
                    ))}
                    {by(type).length === 0 && !loading && <div className="text-xs text-muted-foreground italic">None found yet</div>}
                  </div>
                </div>
              ))}
            </div>
          )}

          <div className="panel p-4" data-tour="risk">
            <div className="text-[11px] uppercase tracking-wider text-muted-foreground">Composite risk · {ticker}</div>
            <div className="flex items-baseline gap-2 mt-1">
              <span className="font-mono text-4xl font-bold" style={{ color: riskColor }}>{risk}</span>
              <span className="text-muted-foreground text-sm">/ 100</span>
            </div>
            <div className="h-2 rounded-full bg-muted mt-3 overflow-hidden">
              <div className="h-full rounded-full" style={{ width: `${risk}%`, background: riskColor, transition: 'width 1s ease' }} />
            </div>
            <div className="mt-4 space-y-2 text-xs">
              {[
                { icon: Newspaper, label: 'News & political risk', w: '40%' },
                { icon: LineChart, label: 'Technical signals', w: '30%' },
                { icon: Link2, label: 'Supplier contagion', w: '30%' },
              ].map((r) => (
                <div key={r.label} className="flex items-center gap-2">
                  <r.icon size={14} className="text-muted-foreground" />
                  <span className="flex-1">{r.label}</span>
                  <span className="font-mono text-muted-foreground">{r.w}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
