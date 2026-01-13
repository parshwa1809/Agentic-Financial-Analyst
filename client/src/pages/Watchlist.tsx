import { useState, useEffect } from 'react';
import { api } from '@/lib/api';
import { Trash2, Loader2, RefreshCw } from 'lucide-react';

interface Ticker {
  symbol: string;
  name: string;
  is_active?: boolean;
}

export default function Watchlist() {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<Ticker[]>([]);
  const [selected, setSelected] = useState<Record<string, boolean>>({});
  const [activeTickers, setActiveTickers] = useState<Ticker[]>([]);
  const [loading, setLoading] = useState(false);
  const [activating, setActivating] = useState(false);

  useEffect(() => {
    fetchActiveTickers();
  }, []);

  const fetchActiveTickers = async () => {
    try {
      const res = await api.getActiveTickers();
      setActiveTickers(res.data);
    } catch (e) { console.error("Error fetching active tickers:", e); }
  };
  
  const loadUniverse = async () => {
    setLoading(true);
    try {
      const res = await api.getAllTickers();
      setResults(res.data);
    } catch (e) { console.error('Error loading universe:', e); }
    setLoading(false);
  };
  
  const handleSearch = async () => {
    if (!query) return;
    setLoading(true);
    try {
      const res = await api.searchTickers(query);
      setResults(res.data);
    } catch (e) { console.error("Error searching tickers:", e); }
    setLoading(false);
  };

  const toggleSelect = (symbol: string) => {
    setSelected(prev => ({ ...prev, [symbol]: !prev[symbol] }));
  };
  
  const handleActivateSelected = async () => {
    // Filter for checked items
    const symbolsToActivate = Object.keys(selected).filter(s => selected[s]);
    if (symbolsToActivate.length === 0) return;

    setActivating(true);
    
    // Process one by one
    for (const symbol of symbolsToActivate) {
      try {
        await api.activateTicker(symbol);
        console.log(`Verified Activation: ${symbol}`);
      } catch (err) {
        console.error(`Failed to activate ${symbol}`, err);
      }
    }

    // Reset and Refresh EVERYTHING
    setSelected({});
    await fetchActiveTickers(); // Refresh Left Panel
    if (query) await handleSearch(); // Refresh Search Results (Update Green Dots)
    else if (results.length > 0) await loadUniverse();
    
    setActivating(false);
  };

  const handleDeactivate = async (symbol: string) => {
    await api.deactivateTicker(symbol);
    await fetchActiveTickers();
    if (query) await handleSearch();
  };

  return (
    <div className="max-w-[1600px] mx-auto">
      <div className="page-title text-foreground flex items-center gap-2">🌍 Watchlist Manager</div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 mt-4">
        {/* Active Stream Panel */}
        <div className="bg-card p-4 rounded-xl border border-border h-[600px] flex flex-col">
          <div className="card-header-custom panel-title flex justify-between">
            <span>📡 Active Stream</span>
            <button onClick={fetchActiveTickers}><RefreshCw size={16} /></button>
          </div>
          <div className="flex-1 bg-background mt-3 rounded p-3 text-muted-foreground scroll-panel overflow-y-auto">
            {activeTickers.length === 0 ? (
              <p className="text-center text-muted-foreground py-4">No active tickers</p>
            ) : (
              activeTickers.map(t => (
                <div key={t.symbol} className="flex justify-between items-center p-2 border-b border-border last:border-b-0 hover:bg-muted/20">
                  <div>
                    <span className="font-mono text-foreground text-lg font-bold">{t.symbol}</span>
                    <p className="text-xs text-muted-foreground">{t.name}</p>
                  </div>
                  <button onClick={() => handleDeactivate(t.symbol)} className="text-destructive hover:bg-destructive/10 p-2 rounded-full transition-colors">
                    <Trash2 size={18} />
                  </button>
                </div>
              ))
            )}
          </div>
        </div>

        {/* Universe Browser */}
        <div className="lg:col-span-2">
          <div className="bg-card p-4 rounded-xl border border-border">
            <div className="card-header-custom panel-title">🔍 Universe Browser</div>
            <div className="mt-4">
              <div className="flex gap-4 mb-4">
                <input 
                  className="flex-1 bg-muted border border-border rounded px-4 py-2 text-foreground placeholder:text-muted-foreground focus:outline-none focus:border-primary"
                  placeholder="Search Symbol or Name (e.g. TSLA, MSFT)"
                  value={query}
                  onChange={e => setQuery(e.target.value)}
                  onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
                />
                <button onClick={handleSearch} className="btn-activate">Search</button>
              </div>
              
              <button 
                onClick={handleActivateSelected} 
                className={`w-full mb-4 py-3 rounded font-bold transition-all ${
                  Object.values(selected).filter(v => v).length > 0 
                  ? 'bg-primary text-primary-foreground hover:opacity-90' 
                  : 'bg-muted text-muted-foreground cursor-not-allowed'
                }`}
                disabled={activating || Object.values(selected).filter(v => v).length === 0}
              >
                {activating ? (
                  <span className="flex items-center justify-center gap-2"><Loader2 className="animate-spin" /> Activating...</span>
                ) : (
                  `Activate Selected (${Object.values(selected).filter(v => v).length})`
                )}
              </button>

              <div className="overflow-y-auto scroll-panel" style={{maxHeight: '420px'}}>
                <table className="w-full text-left text-sm">
                  <thead className="text-muted-foreground sticky top-0 bg-card z-10 border-b border-border">
                    <tr>
                      <th className="py-2 px-3 w-10">Select</th>
                      <th className="py-2 px-3">Symbol</th>
                      <th className="py-2 px-3">Name</th>
                      <th className="py-2 px-3">Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    {results.length === 0 && query && !loading && (
                      <tr><td colSpan={4} className="py-8 text-center text-muted-foreground">No results found for "{query}"</td></tr>
                    )}
                    {results.map(r => (
                      <tr key={r.symbol} className="border-b border-border hover:bg-muted/50 transition-colors">
                        <td className="py-2 px-3">
                          <input 
                            type="checkbox" 
                            checked={selected[r.symbol] || false}
                            onChange={() => toggleSelect(r.symbol)}
                            className="w-5 h-5 accent-primary cursor-pointer"
                          />
                        </td>
                        <td className="py-2 px-3 font-mono font-bold text-foreground">{r.symbol}</td>
                        <td className="py-2 px-3 text-muted-foreground">{r.name}</td>
                        <td className="py-2 px-3">
                          {r.is_active || activeTickers.find(a => a.symbol === r.symbol) ? (
                            <span className="inline-flex items-center gap-1 text-[hsl(var(--success))] font-bold bg-[hsl(var(--success))]/10 px-2 py-1 rounded text-xs">
                              ● Active
                            </span>
                          ) : (
                            <span className="text-muted-foreground text-xs">○ Inactive</span>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}