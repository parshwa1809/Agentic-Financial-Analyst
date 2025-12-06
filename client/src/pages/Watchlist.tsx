import { useState, useEffect } from 'react';
import { api } from '@/lib/api';
import { Trash2 } from 'lucide-react';

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
    setSelected(prev => ({
      ...prev,
      [symbol]: !prev[symbol],
    }));
  };
  
  const handleActivateSelected = async () => {
    const symbolsToActivate = Object.keys(selected).filter(
      symbol => selected[symbol] && !results.find(r => r.symbol === symbol)?.is_active
    );
    
    setLoading(true);
    for (const symbol of symbolsToActivate) {
      await api.activateTicker(symbol);
    }
    setSelected({});
    await handleSearch();
    await fetchActiveTickers();
    setLoading(false);
  };

  const handleDeactivate = async (symbol: string) => {
    await api.deactivateTicker(symbol);
    await fetchActiveTickers();
    if (query) await handleSearch();
  };

  return (
    <div className="max-w-7xl mx-auto">
      <div className="page-title text-foreground flex items-center gap-2">🌍 Watchlist Manager</div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 mt-4">
        {/* Active Stream Panel */}
        <div className="bg-card p-4 rounded-xl border border-border h-[600px] flex flex-col">
          <div className="card-header-custom panel-title">📡 Active Stream (Click X to Remove)</div>
          <div className="flex-1 bg-background mt-3 rounded p-3 text-muted-foreground scroll-panel overflow-y-auto">
            {activeTickers.length === 0 ? (
              <p className="text-center text-muted-foreground py-4">No active tickers</p>
            ) : (
              activeTickers.map(t => (
                <div key={t.symbol} className="flex justify-between items-center p-2 border-b border-border last:border-b-0">
                  <span className="font-mono text-foreground text-lg">{t.symbol}</span>
                  <span className="text-sm text-muted-foreground">{t.name}</span>
                  <button onClick={() => handleDeactivate(t.symbol)} className="text-destructive hover:opacity-80 p-1 rounded-full bg-muted transition-opacity">
                    <Trash2 size={16} />
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
                  placeholder="Search Symbol or Name (e.g. MSFT)"
                  value={query}
                  onChange={e => setQuery(e.target.value)}
                  onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
                />
                <button onClick={handleSearch} className="btn-activate">Search</button>
                <button onClick={loadUniverse} className="btn-activate">Load Universe</button>
              </div>
              <button 
                onClick={handleActivateSelected} 
                className="btn-activate w-full mb-4" 
                disabled={loading || Object.values(selected).filter(v => v).length === 0}
              >
                {loading ? 'Processing...' : `Activate Selected (${Object.values(selected).filter(v => v).length})`}
              </button>
              <div className="overflow-y-auto scroll-panel" style={{maxHeight: '420px'}}>
                <table className="w-full text-left text-sm">
                  <thead className="text-muted-foreground sticky top-0 bg-card z-10 border-b border-border">
                    <tr>
                      <th className="py-2 px-3 w-10"></th>
                      <th className="py-2 px-3">Symbol</th>
                      <th className="py-2 px-3">Name</th>
                      <th className="py-2 px-3">Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    {results.length === 0 && query && !loading && (
                      <tr><td colSpan={4} className="py-4 text-center text-muted-foreground">No results found for "{query}"</td></tr>
                    )}
                    {results.map(r => (
                      <tr key={r.symbol} className="border-b border-border hover:bg-muted/50 transition-colors">
                        <td className="py-2 px-3">
                          <input 
                            type="checkbox" 
                            checked={selected[r.symbol] || false}
                            onChange={() => toggleSelect(r.symbol)}
                            className="w-4 h-4 accent-primary bg-muted border-border rounded"
                          />
                        </td>
                        <td className="py-2 px-3 font-mono text-foreground">{r.symbol}</td>
                        <td className="py-2 px-3 text-muted-foreground">{r.name}</td>
                        <td className="py-2 px-3">{r.is_active ? <span className="text-[hsl(var(--success))]">● Active</span> : <span className="text-muted-foreground">○ Inactive</span>}</td>
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
