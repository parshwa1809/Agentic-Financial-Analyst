import React, { useState } from 'react';
import { Outlet, Link, useLocation } from 'react-router-dom';
import { 
  LayoutDashboard, 
  BrainCircuit, 
  List, 
  Dumbbell, 
  Menu, 
  X, 
  Rocket 
} from 'lucide-react';

const Layout = () => {
  const [isSidebarOpen, setIsSidebarOpen] = useState(true);
  const location = useLocation();

  const menuItems = [
    { icon: LayoutDashboard, label: 'Live Monitor', path: '/' },
    { icon: BrainCircuit, label: 'Deep Dive', path: '/deepdive' }, // Renamed
    // Analyst Chat removed (it's on the dashboard now)
    { icon: List, label: 'Watchlist', path: '/watchlist' },
    { icon: Dumbbell, label: 'Trading Gym', path: '/gym' },
  ];

  return (
    <div className="flex h-screen bg-gray-900 text-gray-100 font-sans overflow-hidden">
      {/* Sidebar */}
      <aside 
        className={`${
          isSidebarOpen ? 'w-64' : 'w-20'
        } bg-gray-800 border-r border-gray-700 transition-all duration-300 flex flex-col relative z-20`}
      >
        <div className="p-4 flex items-center justify-between">
          <div className={`flex items-center gap-2 ${!isSidebarOpen && 'hidden'}`}>
            <Rocket className="w-6 h-6 text-blue-500" />
            <span className="font-bold text-xl tracking-tight">AI Stock Agent</span>
          </div>
          <button 
            onClick={() => setIsSidebarOpen(!isSidebarOpen)}
            className="p-1.5 hover:bg-gray-700 rounded-lg transition-colors"
          >
            {isSidebarOpen ? <X size={20} /> : <Menu size={20} />}
          </button>
        </div>

        <nav className="flex-1 px-3 py-4 space-y-2">
          {menuItems.map((item) => {
            const isActive = location.pathname === item.path;
            return (
              <Link
                key={item.path}
                to={item.path}
                className={`flex items-center gap-3 px-3 py-3 rounded-xl transition-all duration-200 group ${
                  isActive 
                    ? 'bg-blue-600 text-white shadow-lg shadow-blue-900/20' 
                    : 'text-gray-400 hover:bg-gray-700/50 hover:text-white'
                }`}
              >
                <item.icon className={`w-5 h-5 ${isActive ? 'text-white' : 'text-gray-400 group-hover:text-white'}`} />
                {isSidebarOpen && <span className="font-medium">{item.label}</span>}
              </Link>
            );
          })}
        </nav>

        {/* System Status Footer */}
        <div className={`p-4 border-t border-gray-700 ${!isSidebarOpen && 'hidden'}`}>
          <div className="flex items-center gap-3 bg-gray-900/50 p-3 rounded-lg border border-gray-700/50">
            <div className="relative">
              <div className="w-2.5 h-2.5 bg-emerald-500 rounded-full animate-pulse"></div>
              <div className="absolute inset-0 bg-emerald-500 rounded-full blur-sm opacity-50 animate-pulse"></div>
            </div>
            <div>
              <p className="text-xs font-medium text-emerald-400">System Online</p>
              <p className="text-[10px] text-gray-500">Latency: 24ms</p>
            </div>
          </div>
        </div>
      </aside>

      {/* Main Content */}
      <main className="flex-1 overflow-auto relative bg-gray-900">
        <div className="max-w-[1600px] mx-auto p-6">
          <Outlet />
        </div>
      </main>
    </div>
  );
};

export default Layout;