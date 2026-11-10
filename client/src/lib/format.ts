// Shared number formatting + error helpers for the research pages.
export const isNum = (v: unknown): v is number => typeof v === 'number' && Number.isFinite(v);

export const pct = (v?: number | null, d = 1) => (isNum(v) ? `${(v * 100).toFixed(d)}%` : '—');
export const signedPct = (v?: number | null, d = 1) => (isNum(v) ? `${v >= 0 ? '+' : ''}${(v * 100).toFixed(d)}%` : '—');
export const mult = (v?: number | null, d = 2) => (isNum(v) ? `${v.toFixed(d)}x` : '—');
export const num = (v?: number | null, d = 2) => (isNum(v) ? v.toFixed(d) : '—');
export const usd = (v?: number | null, d = 2) => (isNum(v) ? `$${v.toLocaleString('en-US', { minimumFractionDigits: d, maximumFractionDigits: d })}` : '—');

export const money = (v?: number | null) => {
  if (!isNum(v)) return '—';
  const a = Math.abs(v), s = v < 0 ? '−' : '';
  if (a >= 1e12) return `${s}$${(a / 1e12).toFixed(2)}T`;
  if (a >= 1e9) return `${s}$${(a / 1e9).toFixed(2)}B`;
  if (a >= 1e6) return `${s}$${(a / 1e6).toFixed(1)}M`;
  return `${s}$${a.toLocaleString('en-US', { maximumFractionDigits: 2 })}`;
};

export const byUnit = (v: number | null | undefined, unit: string) =>
  unit === '%' ? pct(v) : unit === 'x' ? mult(v) : unit === '$' ? money(v) : num(v);

// eslint-disable-next-line @typescript-eslint/no-explicit-any
export const errMsg = (e: any) =>
  e?.response?.data?.detail || e?.message || 'Something went wrong — is the API container running?';

export const STATUS_DOT: Record<string, string> = {
  ok: 'bg-success', idle: 'bg-info', stale: 'bg-warning', unknown: 'bg-muted-foreground', error: 'bg-destructive',
};
