import axios from 'axios';

// Resolve API base URL
function resolveBase() {
  try {
    if (typeof window !== 'undefined' && (window as any).__API_BASE__) {
      return (window as any).__API_BASE__;
    }
  } catch (e) {}
  const meta = (import.meta as any)?.env?.VITE_API_BASE;
  return meta || '/api';
}

const API = axios.create({
  baseURL: resolveBase(),
});

export const api = {
  getCandles: (ticker: string, timeframe: string) => 
    API.get(`/market/${ticker}/candles?timeframe=${timeframe}`),
  getStats: (ticker: string) => 
    API.get(`/market/${ticker}/stats`),
  getAlerts: (ticker?: string) => 
    API.get(`/market/alerts${ticker ? `?ticker=${ticker}` : ''}`),
  getNews: (ticker?: string) => 
    API.get(`/market/news?ticker=${ticker || ''}`),
  getSupplyChain: (ticker: string, depth = 1, verifiedOnly = false) =>
    API.get(`/market/${ticker}/supply-chain?depth=${depth}${verifiedOnly ? '&verified_only=true' : ''}`),
  
  getActiveTickers: () => 
    API.get('/tickers/active'),
  searchTickers: (query: string) => 
    API.get(`/tickers/search?q=${query}`),
  getAllTickers: () =>
    API.get('/tickers/all'),
  activateTicker: (symbol: string) => 
    API.post(`/tickers/${symbol}/activate`),
  researchNow: (symbol: string) =>
    API.post(`/tickers/${symbol}/research`),
  deactivateTicker: (symbol: string) => 
    API.post(`/tickers/${symbol}/deactivate`),
  
  // --- FIX 1: URL changed to '/chat/ask' ---
  // --- FIX 2: Payload key changed from 'query' to 'message' ---
  chat: (message: string, ticker?: string) => 
    API.post('/chat/ask', { message, ticker }),

  runCouncil: (ticker: string, refresh = false) =>
    API.post(`/council/run`, { ticker, refresh }, { timeout: 240000 }),

  // --- system status (real heartbeats + market session) ---
  getSystemStatus: (ticker?: string) =>
    API.get(`/system/status${ticker ? `?ticker=${ticker}` : ''}`),

  // --- research module (Company Report, Risk, Portfolio Lab, Project Evaluator, Validator) ---
  getCompanyReport: (ticker: string, peers?: string) =>
    API.get(`/research/${ticker}/report${peers ? `?peers=${encodeURIComponent(peers)}` : ''}`, { timeout: 120000 }),
  getPriceCheck: (ticker: string, since?: string) =>
    API.get(`/research/${ticker}/price-check`, { params: since ? { since } : {}, timeout: 120000 }),
  getPriceHistory: (ticker: string) =>
    API.get(`/research/${ticker}/history`, { timeout: 120000 }),
  analyzePortfolio: (body: { tickers: string[]; weights?: Record<string, number>; budget: number; years: number }) =>
    API.post('/research/portfolio', body, { timeout: 120000 }),
  // --- alerts & brief ---
  getEvents: (params?: { ticker?: string; unread_only?: boolean; limit?: number }) => API.get('/alerts', { params }),
  getUnreadCount: () => API.get('/alerts/unread-count'),
  markAlertRead: (id: number) => API.post(`/alerts/${id}/read`),
  markAllAlertsRead: () => API.post('/alerts/read-all'),
  scanAlerts: () => API.post('/alerts/scan', null, { timeout: 180000 }),
  getBrief: (refresh = false) => API.get('/alerts/brief', { params: { refresh }, timeout: 180000 }),
  // --- AI quality ---
  getEvalSummary: (days = 7) => API.get('/evals/summary', { params: { days } }),
  runEvals: (ticker: string, limit = 10) => API.post('/evals/run', null, { params: { ticker, limit }, timeout: 600000 }),
  getEvalRun: (id: number) => API.get(`/evals/runs/${id}`),
  getValuation: (ticker: string) => API.get(`/research/${ticker}/valuation`, { timeout: 180000 }),
  getModelPortfolio: (ticker: string, budget = 100000) => API.get(`/research/${ticker}/model-portfolio`, { params: { budget }, timeout: 180000 }),
  getGlossary: () => API.get('/research/glossary'),
  getWatchlistSummary: () =>
    API.get('/research/watchlist/summary', { timeout: 240000 }),
};