import { Toaster } from "@/components/ui/toaster";
import { Toaster as Sonner } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import Header from "@/components/Header";
import Dashboard from "@/pages/Dashboard";
import ScanToken from "@/pages/ScanToken";
import Watchlist from "@/pages/Watchlist";
import NotFound from "./pages/NotFound";
import { WatchlistProvider } from "@/context/WatchlistContext";

const queryClient = new QueryClient();

const App = () => (
  <QueryClientProvider client={queryClient}>
    <TooltipProvider>
      <Toaster />
      <Sonner />
      <BrowserRouter>
        <WatchlistProvider>
          <div className="dark min-h-screen bg-background text-foreground">
            <Header />
            <Routes>
              <Route path="/" element={<Dashboard />} />
              <Route path="/scan" element={<ScanToken />} />
              <Route path="/watchlist" element={<Watchlist />} />
              <Route path="*" element={<NotFound />} />
            </Routes>
          </div>
        </WatchlistProvider>
      </BrowserRouter>
    </TooltipProvider>
  </QueryClientProvider>
);

export default App;
