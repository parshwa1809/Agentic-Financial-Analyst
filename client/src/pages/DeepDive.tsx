import { useState, useEffect } from 'react';
import { api } from '@/lib/api';
import { ArrowRightLeft } from 'lucide-react';

interface Ticker {
  symbol: string;
  name: string;
}

interface ChainLink {
  type: 'SUPPLIER' | 'CUSTOMER';
  target: string;
}

interface Chain {
  nodes: unknown[];
  links: ChainLink[];
}

export default function DeepDive() {
  const [ticker, setTicker] = useState('');
  const [availableTickers, setAvailableTickers] = useState<Ticker[]>([]);
  const [chain, setChain] = useState<Chain>({ nodes: [], links: [] });
  const [riskScore, setRiskScore] = useState(0);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    api.getActiveTickers().then(res => {
      setAvailableTickers(res.data);
      if (res.data.length > 0) {
        const defaultTicker = res.data[0].symbol;
        setTicker(defaultTicker);
        loadData(defaultTicker);
      }
    }).catch(() => {});
  }, []);

  const loadData = async (sym: string) => {
    if (!sym) return;
    setLoading(true);
    try {
      const res = await api.getSupplyChain(sym);
      const stats = await api.getStats(sym);
      setChain(res.data);
      setRiskScore(stats.data.risk_score || 0);
    } catch (e) { console.error(e); }
    setLoading(false);
  };

  const handleSelectChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const newTicker = e.target.value;
    setTicker(newTicker);
    loadData(newTicker);
  };

  const riskColor = riskScore > 70 
    ? 'bg-destructive' 
    : riskScore > 30 
      ? 'bg-[hsl(var(--warning))]' 
      : 'bg-[hsl(var(--success))]';
      
  const riskTextColor = riskScore > 70 
    ? 'text-destructive' 
    : riskScore > 30 
      ? 'text-[hsl(var(--warning))]' 
      : 'text-[hsl(var(--success))]';

  return (
    <div className="max-w-7xl mx-auto">
      <div className="page-title text-foreground mb-6">🔗 Deep Dive</div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        {/* Left Control Panel */}
        <div className="md:col-span-1 space-y-6">
          <div className="bg-card p-6 rounded-xl border border-border">
            <h3 className="text-lg font-bold text-foreground mb-4 border-b border-border pb-2">Target Asset</h3>
            <select 
              value={ticker} 
              onChange={handleSelectChange}
              className="w-full bg-background border border-border px-4 py-2 rounded text-foreground focus:outline-none focus:border-primary font-mono"
              disabled={loading || availableTickers.length === 0}
            >
              {availableTickers.length === 0 ? (
                <option>No Active Tickers</option>
              ) : (
                availableTickers.map(t => <option key={t.symbol} value={t.symbol}>{t.symbol} - {t.name}</option>)
              )}
            </select>
          </div>

          <div className="bg-card p-6 rounded-xl border border-border">
            <h3 className="text-lg font-bold text-foreground mb-4 border-b border-border pb-2">Political Risk Score</h3>
            <div className="relative h-8 bg-muted rounded-full overflow-hidden">
              <div 
                className={`h-full transition-all duration-1000 ${riskColor}`}
                style={{ width: `${Math.min(riskScore, 100)}%` }}
              />
              <div className="absolute inset-0 flex items-center justify-center font-bold text-foreground drop-shadow-md">
                {loading ? 'Loading...' : `Score: ${riskScore.toFixed(1)} / 100`}
              </div>
            </div>
            <p className={`text-sm mt-3 ${riskTextColor}`}>
              {riskScore > 70 ? 'High Risk' : riskScore > 30 ? 'Moderate Risk' : 'Low Risk'}
            </p>
          </div>
        </div>

        {/* Right Supply Chain Map Panel */}
        <div className="md:col-span-2">
          <div className="bg-card p-6 rounded-xl border border-border">
            <h3 className="text-xl font-bold text-foreground mb-4">⛓️ Supply Chain Map for {ticker}</h3>
            
            {loading && <div className="text-center text-muted-foreground py-10">Loading supply chain data...</div>}
            
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mt-4">
              <div className="bg-background/50 p-4 rounded-xl border border-border">
                <h4 className="text-lg font-bold text-[hsl(var(--success))] mb-3 border-b border-border pb-2">Incoming (Suppliers)</h4>
                <div className="space-y-3 scroll-panel overflow-y-auto" style={{maxHeight: '350px'}}>
                  {chain.links.filter(l => l.type === 'SUPPLIER').map((l, i) => (
                    <div key={i} className="flex items-center justify-between bg-muted p-3 rounded border border-border">
                      <span className="font-bold text-foreground">{l.target}</span>
                      <ArrowRightLeft size={16} className="text-muted-foreground mx-2" />
                      <span className="text-sm text-muted-foreground">Supplies {ticker}</span>
                    </div>
                  ))}
                  {chain.links.filter(l => l.type === 'SUPPLIER').length === 0 && !loading && 
                    <p className="text-muted-foreground text-center">No supplier data found.</p>
                  }
                </div>
              </div>

              <div className="bg-background/50 p-4 rounded-xl border border-border">
                <h4 className="text-lg font-bold text-primary mb-3 border-b border-border pb-2">Outgoing (Customers)</h4>
                <div className="space-y-3 scroll-panel overflow-y-auto" style={{maxHeight: '350px'}}>
                  {chain.links.filter(l => l.type === 'CUSTOMER').map((l, i) => (
                    <div key={i} className="flex items-center justify-between bg-muted p-3 rounded border border-border">
                      <span className="text-sm text-muted-foreground">{ticker} Supplies</span>
                      <ArrowRightLeft size={16} className="text-muted-foreground mx-2" />
                      <span className="font-bold text-foreground">{l.target}</span>
                    </div>
                  ))}
                  {chain.links.filter(l => l.type === 'CUSTOMER').length === 0 && !loading && 
                    <p className="text-muted-foreground text-center">No customer data found.</p>
                  }
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
