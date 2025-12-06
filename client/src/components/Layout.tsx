import { useState } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { LayoutDashboard, List, MessageSquare, Network, Dumbbell, Menu, X, Rocket } from 'lucide-react';

interface SidebarItemProps {
  to: string;
  icon: React.ElementType;
  label: string;
  active: boolean;
  onClick: () => void;
}

const SidebarItem = ({ to, icon: Icon, label, active, onClick }: SidebarItemProps) => (
  <Link 
    to={to} 
    onClick={onClick}
    className={`flex items-center gap-3 px-4 py-3 rounded-lg transition-colors ${
      active ? 'bg-primary text-primary-foreground' : 'text-muted-foreground hover:bg-muted hover:text-foreground'
    }`}
  >
    <Icon size={18} />
    <span className="font-medium">{label}</span>
  </Link>
);

interface LayoutProps {
  children: React.ReactNode;
}

export default function Layout({ children }: LayoutProps) {
  const location = useLocation();
  const [open, setOpen] = useState(false);

  const close = () => setOpen(false);
  const toggle = () => setOpen(v => !v);

  return (
    <div className="min-h-screen bg-background text-foreground">
      {/* Top navbar */}
      <div className="w-full bg-[hsl(222,47%,5%)] border-b border-border fixed top-0 left-0 z-50 h-[60px]">
        <div className="h-full flex items-center justify-center relative">
          <button onClick={toggle} className="absolute left-4 top-1/2 -translate-y-1/2 text-foreground p-2 hover:bg-muted rounded-lg transition-colors">
            {open ? <X /> : <Menu />}
          </button>
          <div className="text-foreground font-bold text-xl flex items-center gap-3">
            <Rocket size={20} className="text-primary" />
            <span>AI Stock Agent</span>
          </div>
        </div>
      </div>
      
      {/* Accent line */}
      <div className="fixed top-[60px] left-0 right-0 z-40 h-1 bg-primary/20" />

      <div className="flex pt-[64px]">
        {/* Offcanvas Backdrop */}
        {open && <div className="offcanvas-backdrop" onClick={close} />}
        
        {/* Sidebar */}
        <div className={`fixed inset-y-0 left-0 z-40 w-64 transform bg-card border-r border-border transition-transform duration-300 ${open ? 'translate-x-0' : '-translate-x-full'}`}>
          <div className="p-4 pt-20">
            <h3 className="text-lg text-foreground font-semibold mb-4 border-b border-border pb-2">Menu</h3>
            <nav className="flex flex-col gap-2">
              <SidebarItem to="/" icon={LayoutDashboard} label="Live Monitor" active={location.pathname === '/'} onClick={close} />
              <SidebarItem to="/watchlist" icon={List} label="Watchlist" active={location.pathname === '/watchlist'} onClick={close} />
              <SidebarItem to="/deep-dive" icon={Network} label="Deep Dive" active={location.pathname === '/deep-dive'} onClick={close} />
              <SidebarItem to="/gym" icon={Dumbbell} label="Trading Gym" active={location.pathname === '/gym'} onClick={close} />
            </nav>
          </div>
        </div>

        {/* Main content area */}
        <main className="flex-1 p-4 md:p-6 min-h-[calc(100vh-64px)]">
          {children}
        </main>
      </div>
    </div>
  );
}
