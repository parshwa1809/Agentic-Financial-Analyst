import { useCallback, useEffect, useState } from 'react';
import { api } from '@/lib/api';

export interface WatchItem { symbol: string; name?: string }

/** Live watchlist (tickers with is_active=1). Polls so every page follows adds/removes automatically. */
export function useWatchlist(pollMs = 15000) {
  const [items, setItems] = useState<WatchItem[]>([]);
  const [loaded, setLoaded] = useState(false);

  const refresh = useCallback(() =>
    api.getActiveTickers()
      .then((r) => {
        const list: WatchItem[] = (Array.isArray(r.data) ? r.data : [])
          .map((t: WatchItem) => ({ symbol: String(t.symbol).toUpperCase(), name: t.name }))
          .sort((a: WatchItem, b: WatchItem) => a.symbol.localeCompare(b.symbol));
        setItems((prev) => (prev.map((p) => p.symbol).join() === list.map((p) => p.symbol).join() ? prev : list));
      })
      .catch(() => {})
      .finally(() => setLoaded(true)), []);

  useEffect(() => {
    refresh();
    const id = setInterval(refresh, pollMs);
    return () => clearInterval(id);
  }, [refresh, pollMs]);

  const add = async (symbol: string) => { await api.activateTicker(symbol.toUpperCase()); await refresh(); };
  const remove = async (symbol: string) => { await api.deactivateTicker(symbol.toUpperCase()); await refresh(); };

  return { items, symbols: items.map((i) => i.symbol), loaded, refresh, add, remove };
}
