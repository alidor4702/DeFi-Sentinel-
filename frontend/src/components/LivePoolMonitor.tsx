import { useEffect, useState, useCallback } from "react";
import { Activity, Loader2, RefreshCw, Star } from "lucide-react";
import { fetchTokens, refreshTokens, TokenListItem } from "@/lib/api";
import { useWatchlist } from "@/context/WatchlistContext";

const POLL_INTERVAL = 60_000; // 60 seconds

function formatAge(hours: number | null): string {
  if (hours === null || hours === undefined) return "—";
  if (hours < 1) return `${Math.max(1, Math.round(hours * 60))}m`;
  if (hours < 24) return `${Math.round(hours)}h`;
  if (hours < 168) return `${Math.round(hours / 24)}d`;
  return `${Math.round(hours / 168)}w`;
}

const LivePoolMonitor = () => {
  const [tokens, setTokens] = useState<TokenListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState(false);
  const { addToWatchlist, removeFromWatchlist, isInWatchlist } = useWatchlist();

  const load = useCallback(async () => {
    try {
      const data = await fetchTokens();
      setTokens(data);
      setError(false);
    } catch {
      setError(true);
    } finally {
      setLoading(false);
    }
  }, []);

  const handleRefresh = useCallback(async () => {
    setRefreshing(true);
    try {
      const data = await refreshTokens();
      setTokens(data);
      setError(false);
    } catch {
      // silent — don't overwrite existing tokens on error
    } finally {
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    const delay = tokens.length === 0 ? 5_000 : POLL_INTERVAL;
    const interval = setInterval(load, delay);
    return () => clearInterval(interval);
  }, [load, tokens.length]);

  // Real-time WebSocket (enhances polling with instant push)
  useEffect(() => {
    let ws: WebSocket | null = null;
    try {
      const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
      ws = new WebSocket(`${proto}//${window.location.host}/ws`);
      ws.onmessage = (event) => {
        try {
          const msg = JSON.parse(event.data);
          if (msg.type === "tokens" && Array.isArray(msg.data)) {
            setTokens(msg.data);
            setError(false);
            setLoading(false);
          } else if (msg.type === "new_token" && msg.data) {
            setTokens((prev) => [msg.data, ...prev].slice(0, 30));
          }
        } catch { /* ignore */ }
      };
    } catch { /* WS not available, polling continues */ }
    return () => { try { ws?.close(); } catch {} };
  }, []);

  return (
    <div className="rounded-xl border border-border bg-card p-5">
      <div className="mb-4 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Activity className="h-4 w-4 text-primary" />
          <h2 className="text-sm font-semibold text-foreground">Live Pool Monitor</h2>
        </div>
        <span className="flex items-center gap-1.5 text-xs text-muted-foreground">
          <span className="relative flex h-1.5 w-1.5">
            <span className="absolute inline-flex h-full w-full animate-pulse-live rounded-full bg-safe" />
            <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-safe" />
          </span>
          {loading ? "Loading..." : `${tokens.length} tokens`}
        </span>
        <button
          onClick={handleRefresh}
          disabled={refreshing}
          className="rounded-md p-1 text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground disabled:opacity-50"
        >
          <RefreshCw className={`h-3.5 w-3.5 ${refreshing ? "animate-spin" : ""}`} />
        </button>
      </div>

      {/* Header row */}
      <div className="mb-2 grid grid-cols-[2fr_1fr_1fr_1fr_1fr_auto_auto] gap-3 border-b border-border px-2 pb-2 text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
        <span>Token</span>
        <span>Liquidity</span>
        <span>Risk</span>
        <span>Verdict</span>
        <span>Launched</span>
        <span className="w-8" />
        <span className="w-8" />
      </div>

      {/* Loading state */}
      {loading && tokens.length === 0 && (
        <div className="flex items-center justify-center py-12">
          <Loader2 className="h-6 w-6 animate-spin text-primary" />
          <span className="ml-2 text-sm text-muted-foreground">Discovering tokens...</span>
        </div>
      )}

      {/* Error / waiting state */}
      {!loading && tokens.length === 0 && (
        <div className="flex flex-col items-center justify-center py-12 text-center">
          <Loader2 className="h-6 w-6 animate-spin text-primary" />
          <span className="mt-2 text-sm text-muted-foreground">
            {error
              ? "Backend unavailable — retrying every 5s..."
              : "Waiting for first scans to complete..."}
          </span>
        </div>
      )}

      {/* Token rows */}
      <div className="space-y-1">
        {tokens.slice(0, 15).map((token) => {
          const starred = isInWatchlist(token.mint);
          return (
            <div
              key={token.id}
              onClick={() => window.open(token.geckoTerminalUrl, "_blank", "noopener,noreferrer")}
              className="animate-slide-in-bottom grid cursor-pointer grid-cols-[2fr_1fr_1fr_1fr_1fr_auto_auto] items-center gap-3 rounded-lg px-2 py-2.5 transition-colors hover:bg-secondary/50"
            >
              {/* Token info */}
              <div className="flex items-center gap-2.5">
                <div
                  className="flex h-8 w-8 items-center justify-center rounded-full text-[10px] font-bold text-white"
                  style={{ backgroundColor: token.color }}
                >
                  {token.symbol.slice(0, 2)}
                </div>
                <div>
                  <p className="text-sm font-medium text-foreground">{token.name}</p>
                  <p className="font-mono text-[10px] text-muted-foreground">
                    {token.mint.slice(0, 4)}...{token.mint.slice(-4)}
                  </p>
                </div>
              </div>

              {/* Liquidity */}
              <span className="text-xs tabular-nums text-foreground">
                {token.liquidity >= 1_000_000
                  ? `$${(token.liquidity / 1_000_000).toFixed(1)}M`
                  : token.liquidity >= 1_000
                  ? `$${(token.liquidity / 1_000).toFixed(1)}K`
                  : `$${token.liquidity.toFixed(0)}`}
              </span>

              {/* Risk bar */}
              <div className="flex items-center gap-2">
                <div className="h-1.5 w-full max-w-[60px] overflow-hidden rounded-full bg-secondary">
                  <div
                    className="h-full rounded-full transition-all duration-500"
                    style={{
                      width: `${token.riskScore}%`,
                      backgroundColor: token.riskScore > 50 ? "hsl(0 84% 60%)" : "hsl(160 84% 39%)",
                    }}
                  />
                </div>
              </div>

              {/* Verdict */}
              <span
                className={`inline-flex w-fit items-center rounded-full px-2 py-0.5 text-[10px] font-bold ${
                  token.riskScore > 50
                    ? "bg-danger/15 text-danger"
                    : "bg-safe/15 text-safe"
                }`}
              >
                {token.riskScore > 50 ? `${token.riskScore}% RUG` : `${token.riskScore}% SAFE`}
              </span>

              {/* Launched */}
              <span className="text-xs tabular-nums text-muted-foreground">
                {formatAge(token.poolAgeHours)}
              </span>

              {/* External link indicator */}
              <span className="w-8 text-right text-muted-foreground">&uarr;</span>

              {/* Star button */}
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  if (starred) {
                    removeFromWatchlist(token.mint);
                  } else {
                    addToWatchlist({
                      mint: token.mint,
                      name: token.name,
                      symbol: token.symbol,
                      riskScore: token.riskScore,
                      liquidity: token.liquidity,
                      geckoTerminalUrl: token.geckoTerminalUrl,
                      price: token.price,
                      poolAgeHours: token.poolAgeHours,
                      color: token.color,
                      addedAt: Date.now(),
                    });
                  }
                }}
                className={`flex w-8 items-center justify-center transition-colors ${
                  starred ? "text-primary hover:text-primary/70" : "text-muted-foreground hover:text-primary"
                }`}
              >
                <Star className={`h-4 w-4 ${starred ? "fill-current" : ""}`} />
              </button>
            </div>
          );
        })}
      </div>
    </div>
  );
};

export default LivePoolMonitor;
