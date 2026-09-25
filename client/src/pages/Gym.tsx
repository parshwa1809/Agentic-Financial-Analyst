import { Dumbbell } from 'lucide-react';

export default function Gym() {
  return (
    <div className="grid place-items-center h-[70vh]">
      <div className="panel p-10 text-center max-w-md">
        <div className="mx-auto grid place-items-center w-14 h-14 rounded-2xl bg-primary/15 text-primary"><Dumbbell /></div>
        <h1 className="text-2xl font-bold mt-4">Trading Gym</h1>
        <p className="text-muted-foreground mt-2 text-sm">A reinforcement-learning sandbox to paper-trade strategies against replayed market data.</p>
        <span className="inline-block mt-4 chip text-warning">Coming soon</span>
      </div>
    </div>
  );
}
