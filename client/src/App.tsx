import { Toaster } from "@/components/ui/toaster";
import { Toaster as Sonner } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import Layout from "@/components/Layout";
import Dashboard from "@/pages/Dashboard";
import Watchlist from "@/pages/Watchlist";
import Chat from "@/pages/Chat";
import DeepDive from "@/pages/DeepDive";
import CompanyReport from "@/pages/CompanyReport";
import PortfolioLab from "@/pages/PortfolioLab";
import Alerts from "@/pages/Alerts";
import Evals from "@/pages/Evals";
import NotFound from "@/pages/NotFound";

const queryClient = new QueryClient();

const App = () => (
  <QueryClientProvider client={queryClient}>
    <TooltipProvider>
      <Toaster />
      <Sonner />
      <BrowserRouter>
        <Routes>
          {/* FIX: Layout is now a Parent Route, not a Wrapper */}
          <Route element={<Layout />}>
            <Route path="/" element={<Dashboard />} />
            <Route path="/watchlist" element={<Watchlist />} />
            <Route path="/chat" element={<Chat />} />
            <Route path="/deepdive" element={<DeepDive />} />
            <Route path="/report" element={<CompanyReport />} />
            <Route path="/portfolio" element={<PortfolioLab />} />
            <Route path="/valuation" element={<Navigate to="/report" replace />} />
            <Route path="/alerts" element={<Alerts />} />
            <Route path="/evals" element={<Evals />} />
            <Route path="/capbudget" element={<Navigate to="/report" replace />} />
            <Route path="/validate" element={<Navigate to="/" replace />} />
            {/* Trading Gym removed: Oracle is an analyst platform and never trades */}
            <Route path="/gym" element={<Navigate to="/" replace />} />
            <Route path="*" element={<NotFound />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </TooltipProvider>
  </QueryClientProvider>
);

export default App;