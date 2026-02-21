import { createContext, useContext, useState, useCallback, ReactNode } from "react";

export interface WatchlistToken {
  mint: string;
  name: string;
  symbol: string;
  riskScore: number;
  liquidity?: number;
  geckoTerminalUrl?: string;
  price?: number | null;
  poolAgeHours?: number | null;
  color?: string;
  addedAt: number;
}

interface WatchlistContextValue {
  addToWatchlist: (token: WatchlistToken) => void;
  removeFromWatchlist: (mint: string) => void;
  isInWatchlist: (mint: string) => boolean;
  watchlistTokens: WatchlistToken[];
}

const WatchlistContext = createContext<WatchlistContextValue | null>(null);

export const WatchlistProvider = ({ children }: { children: ReactNode }) => {
  const [tokens, setTokens] = useState<Map<string, WatchlistToken>>(new Map());

  const addToWatchlist = useCallback((token: WatchlistToken) => {
    setTokens((prev) => new Map(prev).set(token.mint, token));
  }, []);

  const removeFromWatchlist = useCallback((mint: string) => {
    setTokens((prev) => {
      const next = new Map(prev);
      next.delete(mint);
      return next;
    });
  }, []);

  const isInWatchlist = useCallback((mint: string) => tokens.has(mint), [tokens]);

  const watchlistTokens = Array.from(tokens.values());

  return (
    <WatchlistContext.Provider value={{ addToWatchlist, removeFromWatchlist, isInWatchlist, watchlistTokens }}>
      {children}
    </WatchlistContext.Provider>
  );
};

export const useWatchlist = (): WatchlistContextValue => {
  const ctx = useContext(WatchlistContext);
  if (!ctx) throw new Error("useWatchlist must be used within WatchlistProvider");
  return ctx;
};
