interface Ratio {
  key: string;
  label: string;
  value: string | number;
}

interface RatioPanelProps {
  ratios?: Ratio[];
}

export default function RatioPanel({ ratios }: RatioPanelProps) {
  if (!ratios || ratios.length === 0) return null;

  return (
    <div className="grid grid-cols-2 md:grid-cols-4 gap-4 w-full">
      {ratios.map((r) => (
        <div key={r.key} className="bg-background/50 p-3 rounded-lg border border-border flex flex-col items-center justify-center text-center">
          <span className="text-xs text-muted-foreground uppercase font-semibold tracking-wider">{r.label}</span>
          <span className="text-lg font-bold text-foreground mt-1">{r.value}</span>
        </div>
      ))}
    </div>
  );
}
