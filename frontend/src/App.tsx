import { Toaster } from "@/components/ui/toaster";
import { Toaster as Sonner } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import { AuthProvider } from "@/hooks/useAuth";
import Header from "@/components/Header";
import Dashboard from "@/pages/Dashboard";
import ScanToken from "@/pages/ScanToken";
import Connect from "@/pages/Connect";
import Watchlist from "@/pages/Watchlist";
import Attestations from "@/pages/Attestations";
import WalletRisk from "@/pages/WalletRisk";
import NotFound from "./pages/NotFound";
import { WatchlistProvider } from "@/context/WatchlistContext";
import SolanaWalletProvider from "@/components/SolanaWalletProvider";

const queryClient = new QueryClient();

const App = () => (
  <QueryClientProvider client={queryClient}>
    <SolanaWalletProvider>
      <TooltipProvider>
        <Toaster />
        <Sonner />
        <BrowserRouter>
          <AuthProvider>
            <WatchlistProvider>
              <div className="dark min-h-screen bg-background text-foreground">
                <Header />
                <Routes>
                  <Route path="/" element={<Dashboard />} />
                  <Route path="/scan" element={<ScanToken />} />
                  <Route path="/scan/:mint" element={<ScanToken />} />
                  <Route path="/connect" element={<Connect />} />
                  <Route path="/watchlist" element={<Watchlist />} />
                  <Route path="/attestations" element={<Attestations />} />
                  <Route path="/wallet-risk" element={<WalletRisk />} />
                  <Route path="*" element={<NotFound />} />
                </Routes>
              </div>
            </WatchlistProvider>
          </AuthProvider>
        </BrowserRouter>
      </TooltipProvider>
    </SolanaWalletProvider>
  </QueryClientProvider>
);

export default App;
