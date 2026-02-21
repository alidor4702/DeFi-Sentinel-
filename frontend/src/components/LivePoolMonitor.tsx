import { useEffect, useState } from "react";
import { Activity } from "lucide-react";
import { MOCK_TOKENS, Token } from "@/data/mockData";

const LivePoolMonitor = () => {
  const [visibleTokens, setVisibleTokens] = useState<Token[]>(MOCK_TOKENS.slice(0, 5));
  const [currentIndex, setCurrentIndex] = useState(5);

  useEffect(() => {
    const interval = setInterval(() => {
      setCurrentIndex((prev) => {
        const next = (prev + 1) % MOCK_TOKENS.length;
        const newToken = { ...MOCK_TOKENS[next], id: `${MOCK_TOKENS[next].id}-${Date.now()}`, timeAgo: "1s ago" };
        setVisibleTokens((tokens) => [newToken, ...tokens.slice(0, 7)]);
        return next;
      });
    }, 4000);
    return () => clearInterval(interval);
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
          Streaming
        </span>
      </div>

      {/* Header row */}
      <div className="mb-2 grid grid-cols-[2fr_1fr_1fr_1fr_1fr_auto] gap-3 border-b border-border px-2 pb-2 text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
        <span>Token</span>
        <span>Holders</span>
        <span>Liquidity</span>
        <span>Risk</span>
        <span>Verdict</span>
        <span className="w-14 text-right">Time</span>
      </div>

      {/* Token rows */}
      <div className="space-y-1">
        {visibleTokens.map((token) => (
          <div
            key={token.id}
            className="animate-slide-in-bottom grid grid-cols-[2fr_1fr_1fr_1fr_1fr_auto] items-center gap-3 rounded-lg px-2 py-2.5 transition-colors hover:bg-secondary/50"
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

            {/* Holders */}
            <span className="text-xs tabular-nums text-foreground">
              {token.holders >= 1000 ? `${(token.holders / 1000).toFixed(0)}K` : token.holders}
            </span>

            {/* Liquidity */}
            <span className="text-xs tabular-nums text-foreground">
              {token.liquidity >= 1000000
                ? `$${(token.liquidity / 1000000).toFixed(1)}M`
                : token.liquidity >= 1000
                ? `$${(token.liquidity / 1000).toFixed(1)}K`
                : `$${token.liquidity}`}
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

            {/* Time */}
            <span className="w-14 text-right text-[10px] text-muted-foreground">
              {token.timeAgo}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
};

export default LivePoolMonitor;
