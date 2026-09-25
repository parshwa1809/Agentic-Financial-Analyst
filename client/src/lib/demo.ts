/**
 * Offline demo mode — `npm run dev:demo`
 *
 * Replaces the HTTP layer with a simulated market so the whole UI runs with
 * no backend, database, Redis, Alpaca keys or Ollama. Prices are a seeded
 * random walk (NOT real market data); news, alerts, supply-chain links and
 * AI answers are canned but shaped exactly like the real API responses.
 */
import type { AxiosAdapter, AxiosResponse, InternalAxiosRequestConfig } from 'axios';

export const IS_DEMO = import.meta.env.VITE_DEMO === '1';

// ---------------------------------------------------------------- utilities
function mulberry32(seed: number) {
  return () => {
    seed |= 0; seed = (seed + 0x6d2b79f5) | 0;
    let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}
const hash = (s: string) => [...s].reduce((h, c) => (Math.imul(h, 31) + c.charCodeAt(0)) | 0, 7);
const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));
const round = (n: number, d = 2) => Math.round(n * 10 ** d) / 10 ** d;

// ---------------------------------------------------------------- universe
interface Profile {
  name: string; price: number; vol: number; drift: number;
  cap: number; pe: number; pb: number; de: number; margin: number; dy: number;
  risk: number;
  suppliers: string[]; customers: string[]; competitors: string[];
}

const PROFILES: Record<string, Profile> = {
  NVDA: { name: 'NVIDIA Corp', price: 181.4, vol: 0.0032, drift: 0.00012, cap: 4.42e12, pe: 51.3, pb: 43.1, de: 0.11, margin: 0.558, dy: 0.0002, risk: 58,
    suppliers: ['TSM', 'MU', 'ASML', 'AMKR'], customers: ['MSFT', 'AMZN', 'GOOGL', 'META', 'ORCL'], competitors: ['AMD', 'INTC', 'AVGO'] },
  AAPL: { name: 'Apple Inc', price: 238.2, vol: 0.0018, drift: 0.00004, cap: 3.54e12, pe: 36.2, pb: 52.8, de: 1.54, margin: 0.243, dy: 0.0044, risk: 41,
    suppliers: ['TSM', 'QCOM', 'AVGO', 'SWKS', 'GLW'], customers: ['BBY', 'TMUS', 'VZ'], competitors: ['GOOGL', 'MSFT'] },
  TSLA: { name: 'Tesla Inc', price: 341.7, vol: 0.0041, drift: -0.00006, cap: 1.1e12, pe: 188.4, pb: 15.2, de: 0.17, margin: 0.063, dy: 0, risk: 72,
    suppliers: ['PCRFY', 'ALB', 'NVDA'], customers: ['HTZ', 'UBER'], competitors: ['RIVN', 'GM', 'F', 'LCID'] },
  MSFT: { name: 'Microsoft Corp', price: 512.6, vol: 0.0015, drift: 0.00007, cap: 3.81e12, pe: 37.9, pb: 11.2, de: 0.33, margin: 0.358, dy: 0.0065, risk: 33,
    suppliers: ['NVDA', 'AMD', 'INTC'], customers: ['ACN', 'IBM'], competitors: ['GOOGL', 'AMZN', 'ORCL', 'CRM'] },
  AMZN: { name: 'Amazon.com Inc', price: 226.9, vol: 0.0022, drift: 0.00005, cap: 2.42e12, pe: 34.6, pb: 7.4, de: 0.46, margin: 0.106, dy: 0, risk: 45,
    suppliers: ['NVDA', 'INTC', 'UPS'], customers: ['SHOP', 'NFLX'], competitors: ['WMT', 'MSFT', 'GOOGL', 'BABA'] },
};

const UNIVERSE: [string, string][] = [
  ['AAPL', 'Apple Inc'], ['ABNB', 'Airbnb Inc'], ['ADBE', 'Adobe Inc'], ['AMD', 'Advanced Micro Devices'],
  ['AMZN', 'Amazon.com Inc'], ['ASML', 'ASML Holding'], ['AVGO', 'Broadcom Inc'], ['BA', 'Boeing Co'],
  ['COIN', 'Coinbase Global'], ['COST', 'Costco Wholesale'], ['CRM', 'Salesforce Inc'], ['CRWD', 'CrowdStrike'],
  ['DIS', 'Walt Disney Co'], ['GOOGL', 'Alphabet Inc'], ['INTC', 'Intel Corp'], ['JPM', 'JPMorgan Chase'],
  ['META', 'Meta Platforms'], ['MSFT', 'Microsoft Corp'], ['MU', 'Micron Technology'], ['NFLX', 'Netflix Inc'],
  ['NVDA', 'NVIDIA Corp'], ['ORCL', 'Oracle Corp'], ['PANW', 'Palo Alto Networks'], ['PLTR', 'Palantir Technologies'],
  ['PYPL', 'PayPal Holdings'], ['QCOM', 'Qualcomm Inc'], ['RIVN', 'Rivian Automotive'], ['SHOP', 'Shopify Inc'],
  ['SNOW', 'Snowflake Inc'], ['SOFI', 'SoFi Technologies'], ['TSLA', 'Tesla Inc'], ['TSM', 'Taiwan Semiconductor'],
  ['UBER', 'Uber Technologies'], ['V', 'Visa Inc'], ['WMT', 'Walmart Inc'],
];
const NAME = Object.fromEntries(UNIVERSE);

const active = new Set<string>(['NVDA', 'AAPL', 'TSLA', 'MSFT']);

function profileFor(sym: string): Profile {
  if (PROFILES[sym]) return PROFILES[sym];
  const r = mulberry32(hash(sym));
  const p: Profile = {
    name: NAME[sym] || sym, price: 40 + r() * 300, vol: 0.002 + r() * 0.002, drift: (r() - 0.45) * 0.0002,
    cap: (20 + r() * 400) * 1e9, pe: 12 + r() * 60, pb: 2 + r() * 12, de: r() * 1.4, margin: 0.05 + r() * 0.3, dy: r() * 0.02,
    risk: Math.round(25 + r() * 50), suppliers: ['TSM', 'INTC'], customers: ['AMZN', 'MSFT'], competitors: ['GOOGL', 'META'],
  };
  PROFILES[sym] = p;
  return p;
}

// ---------------------------------------------------------------- candles
interface Bar { timestamp: string; open: number; high: number; low: number; close: number; volume: number; }
const series: Record<string, Bar[]> = {};
const INTRADAY_STEP = 2 * 60 * 1000; // 2-minute bars

function sessionStart() {
  // "Today" 9:30 local, stretched so the chart always has a full-looking session.
  const d = new Date();
  d.setHours(9, 30, 0, 0);
  return d.getTime();
}

function nextBar(prev: number, p: Profile, rnd: () => number, t: number, volBase: number, scale = 1): Bar {
  const shock = (rnd() + rnd() + rnd() - 1.5) * 1.15;
  const close = prev * (1 + p.drift * scale + p.vol * Math.sqrt(scale) * shock);
  const wick = p.vol * Math.sqrt(scale) * prev;
  const high = Math.max(prev, close) + rnd() * wick * 0.9;
  const low = Math.min(prev, close) - rnd() * wick * 0.9;
  const volume = Math.round(volBase * (0.55 + rnd() * 0.9) * (Math.abs(shock) > 1.2 ? 2.4 : 1));
  return { timestamp: new Date(t).toISOString(), open: round(prev), high: round(high), low: round(low), close: round(close), volume };
}

function intraday(sym: string): Bar[] {
  if (series[sym]) return series[sym];
  const p = profileFor(sym);
  const rnd = mulberry32(hash(sym) ^ 0x9e37);
  const bars: Bar[] = [];
  let px = p.price * 0.985;
  const start = sessionStart();
  for (let i = 0; i < 150; i++) {
    const b = nextBar(px, p, rnd, start + i * INTRADAY_STEP, p.cap / 4e6);
    bars.push(b); px = b.close;
  }
  series[sym] = bars;
  return bars;
}

/** Advance the live session: update the forming bar, occasionally print a new one. */
const tickCount: Record<string, number> = {};
function tick(sym: string) {
  const bars = intraday(sym);
  const p = profileFor(sym);
  const last = bars[bars.length - 1];
  tickCount[sym] = (tickCount[sym] || 0) + 1;
  const rnd = Math.random;
  if (tickCount[sym] % 2 === 0) {
    const b = nextBar(last.close, p, rnd, new Date(last.timestamp).getTime() + INTRADAY_STEP, p.cap / 4e6);
    bars.push(b);
    if (bars.length > 170) bars.shift();
  } else {
    const c = round(last.close * (1 + p.vol * 0.6 * (rnd() - 0.48)));
    last.close = c; last.high = Math.max(last.high, c); last.low = Math.min(last.low, c);
    last.volume += Math.round(p.cap / 4e7 * rnd());
  }
}

function historical(sym: string, days: number, stepHours: number): Bar[] {
  const p = profileFor(sym);
  const rnd = mulberry32(hash(sym + days));
  const n = Math.round((days * 6.5) / stepHours);
  const bars: Bar[] = [];
  let px = p.price * (1 - p.drift * n * stepHours * 5 - (rnd() - 0.5) * 0.06);
  const end = new Date(intraday(sym)[0].timestamp).getTime();
  let t = end - days * 86400000;
  for (let i = 0; i < n; i++) {
    t += stepHours * 3600000;
    const d = new Date(t);
    if (d.getDay() === 0 || d.getDay() === 6) { t += 86400000; continue; }
    const b = nextBar(px, p, rnd, t, (p.cap / 4e6) * stepHours * 20, stepHours * 5);
    bars.push(b); px = b.close;
  }
  // stitch to today's open so the series is continuous
  const k = intraday(sym)[0].open / px;
  return bars.map((b) => ({ ...b, open: round(b.open * k), high: round(b.high * k), low: round(b.low * k), close: round(b.close * k) }));
}

// Same maths as services/indicators.py
function withIndicators(bars: Bar[]) {
  const closes = bars.map((b) => b.close);
  const out = bars.map((b) => ({ ...b } as Bar & Record<string, number>));
  let ema12 = closes[0], ema26 = closes[0], cumPV = 0, cumV = 0;
  for (let i = 0; i < out.length; i++) {
    const c = closes[i];
    ema12 = ema12 + (2 / 13) * (c - ema12);
    ema26 = ema26 + (2 / 27) * (c - ema26);
    out[i].MACD = round(ema12 - ema26, 3);
    const tp = (out[i].high + out[i].low + c) / 3;
    cumPV += tp * out[i].volume; cumV += out[i].volume;
    out[i].VWAP = round(cumPV / cumV);
    if (i >= 14) {
      let g = 0, l = 0;
      for (let j = i - 13; j <= i; j++) { const d = closes[j] - closes[j - 1]; if (d > 0) g += d; else l -= d; }
      out[i].RSI = round(l === 0 ? 100 : 100 - 100 / (1 + g / l), 1);
    }
    if (i >= 19) {
      const w = closes.slice(i - 19, i + 1); const m = w.reduce((a, b) => a + b, 0) / 20;
      const sd = Math.sqrt(w.reduce((a, b) => a + (b - m) ** 2, 0) / 19);
      out[i].BandWidth = round(((4 * sd) / m) * 100, 2);
    }
  }
  return out;
}

function quote(sym: string) {
  const bars = intraday(sym);
  const last = bars[bars.length - 1].close;
  const open = bars[0].open;
  return { price: last, change: round(((last - open) / open) * 100) };
}

// ---------------------------------------------------------------- content
const ago = (min: number) => new Date(Date.now() - min * 60000).toISOString();

function news(sym: string) {
  const n = profileFor(sym).name.replace(/ (Inc|Corp|Co)$/, '');
  const s = profileFor(sym).suppliers[0];
  const c = profileFor(sym).competitors[0];
  const items: [string, number][] = [
    [`${n} shares climb as analysts lift price targets on data-center demand`, 2],
    [`Options traders pile into ${sym} calls ahead of next week's earnings`, 1],
    [`${s} capacity update eases supply concerns for ${n}`, 1],
    [`${c} unveils rival product, putting pressure on ${n}'s margins`, -1],
    [`Regulators widen export-control review; ${sym} among names flagged`, -2],
    [`Institutional ownership of ${sym} rises for third straight quarter`, 1],
    [`${n} guidance seen conservative after strong quarterly beat`, 2],
  ];
  return items.map(([headline, score], i) => ({
    ticker: sym, headline, url: '#', published_at: ago(6 + i * 37), sentiment_score: score,
  }));
}

const alertLog: Record<string, { ticker: string; message: string; created_at: string }[]> = {};
function alerts(sym: string) {
  if (!alertLog[sym]) {
    const p = profileFor(sym);
    alertLog[sym] = [
      { ticker: sym, message: `Bullish VWAP Cross — price reclaimed VWAP on 2.1x volume`, created_at: ago(3) },
      { ticker: sym, message: `2nd-order contagion: ${SECOND[p.suppliers[0]]?.[0]?.[0] ?? 'ASML'} ${moveOf(SECOND[p.suppliers[0]]?.[0]?.[0] ?? 'ASML')}% → supplies ${p.suppliers[0]} → ${sym}`, created_at: ago(9) },
      { ticker: sym, message: `Contagion Watch: key SUPPLIER ${p.suppliers[0]} ${moveOf(p.suppliers[0])}% intraday`, created_at: ago(14) },
      { ticker: sym, message: `RSI Overbought (71.8) — momentum stretched`, created_at: ago(41) },
      { ticker: sym, message: `Bull Trap Warning: price +1.6% but news sentiment negative (-0.4)`, created_at: ago(66) },
    ];
  }
  return alertLog[sym];
}
const LIVE_ALERTS = [
  (s: string) => `Volume Spike: ${(2.6 + Math.random()).toFixed(1)}x 10-bar average`,
  (s: string) => `Price Breakout > Upper Bollinger Band`,
  (s: string) => `Smart-money flow: large block prints on ${s}`,
];
let alertTick = 0;

function stats(sym: string) {
  const p = profileFor(sym);
  const fmtCap = (v: number) => (v >= 1e12 ? `$${(v / 1e12).toFixed(2)}T` : `$${(v / 1e9).toFixed(2)}B`);
  return {
    risk_score: p.risk,
    ratios: [
      { key: 'market_cap', label: 'Market Cap', value: fmtCap(p.cap) },
      { key: 'pe_ratio', label: 'P/E Ratio', value: p.pe.toFixed(2) },
      { key: 'pb_ratio', label: 'P/B Ratio', value: p.pb.toFixed(2) },
      { key: 'debt_to_equity', label: 'Debt/Eq', value: p.de.toFixed(2) },
      { key: 'profit_margin', label: 'Margins', value: `${(p.margin * 100).toFixed(2)}%` },
      { key: 'dividend_yield', label: 'Div Yield', value: `${(p.dy * 100).toFixed(2)}%` },
    ],
  };
}

// Second-order links: the partners' own suppliers / customers (what the
// supply-chain agent discovers when it researches each partner in turn).
const SECOND: Record<string, [string, string][]> = {
  TSM: [['ASML', 'SUPPLIER'], ['AMAT', 'SUPPLIER'], ['LRCX', 'SUPPLIER'], ['AMD', 'CUSTOMER'], ['AAPL', 'CUSTOMER'], ['QCOM', 'CUSTOMER']],
  MU: [['AMAT', 'SUPPLIER'], ['KLAC', 'SUPPLIER']],
  ASML: [['KLAC', 'COMPETITOR']],
  AMKR: [['INTC', 'CUSTOMER']],
  MSFT: [['ORCL', 'COMPETITOR']],
  AMZN: [['NFLX', 'CUSTOMER'], ['SNOW', 'CUSTOMER']],
  GOOGL: [['SNAP', 'CUSTOMER']],
  META: [['SNAP', 'COMPETITOR']],
  QCOM: [['TSM', 'SUPPLIER']],
  AVGO: [['TSM', 'SUPPLIER']],
  SWKS: [['TSM', 'SUPPLIER']],
  PCRFY: [['ALB', 'SUPPLIER']],
  ALB: [['SQM', 'COMPETITOR']],
  RIVN: [['PCRFY', 'SUPPLIER']],
  NVDA: [['TSM', 'SUPPLIER'], ['MU', 'SUPPLIER']],
  INTC: [['ASML', 'SUPPLIER'], ['AMAT', 'SUPPLIER']],
  AMD: [['TSM', 'SUPPLIER']],
  UPS: [['FDX', 'COMPETITOR']],
  WMT: [['COST', 'COMPETITOR']],
};

// Today's moves for names that appear in the network (drives contagion paths)
const MOVES: Record<string, number> = { ASML: -4.1, AMAT: -2.6, LRCX: -1.2, KLAC: -0.8, TSM: -1.9, MU: 0.7, PCRFY: -3.3, ALB: -2.2, AMD: 1.4 };
export const moveOf = (t: string) => MOVES[t] ?? (PROFILES[t] ? quote(t).change : round((mulberry32(hash(t))() - 0.5) * 3));

function supplyChain(sym: string, depth = 1) {
  const p = profileFor(sym);
  const nodes: { id: string; type: string; depth: number; change: number }[] = [{ id: sym, type: 'TARGET', depth: 0, change: moveOf(sym) }];
  const links: { source: string; target: string; type: string; depth: number }[] = [];
  const seen = new Set([sym]);
  const add = (list: string[], type: string) => list.forEach((t) => {
    if (!seen.has(t)) { nodes.push({ id: t, type, depth: 1, change: moveOf(t) }); seen.add(t); }
    links.push({ source: sym, target: t, type, depth: 1 });
  });
  add(p.suppliers, 'SUPPLIER'); add(p.customers, 'CUSTOMER'); add(p.competitors, 'COMPETITOR');
  if (depth >= 2) {
    const first = [...p.suppliers, ...p.customers, ...p.competitors];
    first.forEach((f) => (SECOND[f] || []).forEach(([t, type]) => {
      if (t === sym) return;
      if (!seen.has(t)) { nodes.push({ id: t, type, depth: 2, change: moveOf(t) }); seen.add(t); }
      links.push({ source: f, target: t, type, depth: 2 });
    }));
  }
  return { nodes, links };
}

function chatAnswer(message: string, sym?: string) {
  const t = sym || 'NVDA';
  const p = profileFor(t);
  const q = quote(t);
  const ind = withIndicators(intraday(t));
  const last = ind[ind.length - 1];
  const m = message.toLowerCase();
  if (/supplier|supply|risk|chain|depend/.test(m)) {
    const s1 = p.suppliers[0];
    const s2 = (SECOND[s1] || []).filter(([, ty]) => ty === 'SUPPLIER').map(([x]) => x);
    return `${t}'s biggest dependency is **${s1}** (${moveOf(s1)}% today).\n\n` +
      (s2.length ? `Second-order: ${s1} itself depends on **${s2.join(', ')}**. ${s2[0]} is ${moveOf(s2[0])}% today, so the shock can travel ${s2[0]} → ${s1} → ${t} before it shows up in ${t}'s price.\n\n` : '') +
      `Other suppliers: ${p.suppliers.slice(1).join(', ')}. Largest customers: ${p.customers.slice(0, 3).join(', ')}.\n\n` +
      `Takeaway: supply risk is elevated but not yet showing in ${t}'s price (${q.change >= 0 ? '+' : ''}${q.change}% today).`;
  }
  if (/buy|sell|hold|should|entry/.test(m)) {
    return `Not financial advice, but here's what the data says for ${t}:\n\n` +
      `• Price $${q.price.toFixed(2)} vs VWAP $${last.VWAP} → ${q.price > last.VWAP ? 'buyers in control' : 'sellers in control'}\n` +
      `• RSI ${last.RSI ?? 'n/a'} → ${Number(last.RSI) > 68 ? 'stretched, wait for a pullback' : 'room to run'}\n` +
      `• P/E ${p.pe.toFixed(1)} → ${p.pe > 45 ? 'priced for perfection' : 'reasonable for its growth'}\n\n` +
      `Run the Council for a full bull vs bear debate.`;
  }
  return `${t} is trading at $${q.price.toFixed(2)} (${q.change >= 0 ? '+' : ''}${q.change}% today). ` +
    `RSI is ${last.RSI ?? 'n/a'}, MACD ${Number(last.MACD) > 0 ? 'positive' : 'negative'}, and the composite risk score is ${p.risk}/100. ` +
    `Latest headline: "${news(t)[0].headline}".`;
}

function council(sym: string) {
  const p = profileFor(sym);
  const q = quote(sym);
  const verdict = p.risk > 65 ? 'SELL' : p.pe > 45 ? 'HOLD' : 'BUY';
  const conf = verdict === 'BUY' ? 0.78 : verdict === 'HOLD' ? 0.64 : 0.71;
  const bull = `Momentum is intact: price is above VWAP and ${p.customers.slice(0, 2).join(' and ')} keep expanding orders. Margins of ${(p.margin * 100).toFixed(0)}% leave room to absorb shocks.`;
  const bear = `At ${p.pe.toFixed(0)}x earnings the stock is priced for perfection, and ${p.suppliers[0]} weakness could squeeze supply next quarter.`;
  const analysis = `The Technical Analyst sees trend strength (${q.change >= 0 ? '+' : ''}${q.change}% today), the Fundamental Analyst flags valuation, and the Risk Manager scores exposure at ${p.risk}/100. ` +
    `Net: ${verdict === 'BUY' ? 'accumulate on dips below VWAP' : verdict === 'HOLD' ? 'hold existing positions, no new entries until RSI cools' : 'reduce exposure until supply risk clears'}.`;
  return {
    verdict, decision: verdict, confidence: conf, horizon: 'Short-term (2–4 weeks)', time_horizon: 'Short-term (2–4 weeks)',
    analysis, reasoning: analysis, bull_case: bull, bear_case: bear,
  };
}

// ---------------------------------------------------------------- router
async function route(method: string, path: string, params: URLSearchParams, body: Record<string, string>) {
  let mm: RegExpMatchArray | null;
  if (path === '/tickers/active') return [...active].map((s) => ({ symbol: s, name: profileFor(s).name, ...quote(s) }));
  if (path === '/tickers/all') return UNIVERSE.map(([symbol, name]) => ({ symbol, name, is_active: active.has(symbol) ? 1 : 0 }));
  if (path === '/tickers/search') {
    const q = (params.get('q') || '').toUpperCase();
    return UNIVERSE.filter(([s, n]) => s.includes(q) || n.toUpperCase().includes(q)).slice(0, 10)
      .map(([symbol, name]) => ({ symbol, name, is_active: active.has(symbol) ? 1 : 0 }));
  }
  if ((mm = path.match(/^\/tickers\/([^/]+)\/activate$/))) { await sleep(900); active.add(mm[1].toUpperCase()); return { status: 'success', symbol: mm[1] }; }
  if ((mm = path.match(/^\/tickers\/([^/]+)\/deactivate$/))) { active.delete(mm[1].toUpperCase()); return { status: 'success' }; }

  if ((mm = path.match(/^\/market\/([^/]+)\/candles$/))) {
    const sym = mm[1].toUpperCase();
    const tf = params.get('timeframe') || '1D';
    if (tf === '1Min' || tf === '1D') { tick(sym); return { data: withIndicators(intraday(sym)) }; }
    if (tf === '1W') return { data: withIndicators(historical(sym, 7, 0.5)) };
    return { data: withIndicators(historical(sym, 30, 1)) };
  }
  if ((mm = path.match(/^\/market\/([^/]+)\/stats$/))) return stats(mm[1].toUpperCase());
  if ((mm = path.match(/^\/market\/([^/]+)\/supply-chain$/))) return supplyChain(mm[1].toUpperCase(), Number(params.get('depth') || 1));
  if (path === '/market/alerts') {
    const sym = (params.get('ticker') || 'NVDA').toUpperCase();
    const list = alerts(sym);
    alertTick++;
    if (alertTick % 4 === 0) {
      const f = LIVE_ALERTS[(alertTick / 4) % LIVE_ALERTS.length];
      list.unshift({ ticker: sym, message: f(sym), created_at: new Date().toISOString() });
    }
    return list.slice(0, 12);
  }
  if (path === '/market/news') return news((params.get('ticker') || 'NVDA').toUpperCase());
  if (path === '/chat/ask') { await sleep(1400); return { response: chatAnswer(body.message || '', body.ticker) }; }
  if (path === '/council/run') { await sleep(2600); return { result: council((body.ticker || 'NVDA').toUpperCase()) }; }
  if (path === '/health') return { status: 'ok' };
  throw Object.assign(new Error(`Demo: no route for ${method} ${path}`), { status: 404 });
}

export const demoAdapter: AxiosAdapter = async (config: InternalAxiosRequestConfig) => {
  const url = new URL(config.url || '', 'http://demo.local');
  const params = new URLSearchParams(url.search);
  Object.entries(config.params || {}).forEach(([k, v]) => params.set(k, String(v)));
  let body: Record<string, string> = {};
  try { body = typeof config.data === 'string' ? JSON.parse(config.data) : config.data || {}; } catch { body = {}; }
  await sleep(60 + Math.random() * 90);
  const data = await route((config.method || 'get').toUpperCase(), url.pathname, params, body);
  return { data, status: 200, statusText: 'OK', headers: {}, config, request: {} } as AxiosResponse;
};
