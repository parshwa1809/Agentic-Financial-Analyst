import axios from 'axios';

// Resolve API base URL
function resolveBase() {
  try {
    if (typeof window !== 'undefined' && (window as any).__API_BASE__) {
      return (window as any).__API_BASE__;
    }
  } catch (e) {}
  const meta = (import.meta as any)?.env?.VITE_API_BASE;
  return meta || 'http://localhost:8000/api';
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
  getSupplyChain: (ticker: string) => 
    API.get(`/market/${ticker}/supply-chain`),
  
  getActiveTickers: () => 
    API.get('/tickers/active'),
  searchTickers: (query: string) => 
    API.get(`/tickers/search?q=${query}`),
  getAllTickers: () =>
    API.get('/tickers/all'),
  activateTicker: (symbol: string) => 
    API.post(`/tickers/${symbol}/activate`),
  deactivateTicker: (symbol: string) => 
    API.post(`/tickers/${symbol}/deactivate`),
  
  // --- FIX 1: URL changed to '/chat/ask' ---
  // --- FIX 2: Payload key changed from 'query' to 'message' ---
  chat: (message: string, ticker?: string) => 
    API.post('/chat/ask', { message, ticker }),

  runCouncil: (ticker: string) => 
    API.post(`/council/run`, { ticker }),
};