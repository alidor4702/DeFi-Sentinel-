import { Star } from "lucide-react";
import { useWatchlist } from "@/context/WatchlistContext";

function formatAge(hours: number | null | undefined): string {
  if (hours === null || hours === undefined) return "\u2014";
  if (hours < 1) return `${Math.max(1, Math.round(hours * 60))}m`;
  if (hours < 24) return `${Math.round(hours)}h`;
  if (hours < 168) return `${Math.round(hours / 24)}d`;
  return `${Math.round(hours / 168)}w`;
}

const Watchlist = () => {
  const { watchlistTokens, removeFromWatchlist } = useWatchlist();

  return (
    <main className="container py-8">
      <div className="rounded-xl border border-border bg-card p-5">
        {/* Header */}
        <div className="mb-4 flex items-center gap-2">
          <Star className="h-4 w-4 text-primary" />
          <h2 className="text-sm font-semibold text-foreground">Watchlist</h2>
          <span className="ml-1 text-xs text-muted-foreground">({watchlistTokens.length})</span>
        </div>

        {/* Empty state */}
        {watchlistTokens.length === 0 && (
          <div className="flex flex-col items-center justify-center py-16 text-center">
            <Star className="h-10 w-10 text-muted-foreground/40" />
            <p className="mt-3 text-sm font-medium text-muted-foreground">No tokens in your watchlist</p>
            <p className="mt-1 text-xs text-muted-foreground/60">
              Star tokens from the Live Pool Monitor or Scan Token page to track them here.
            </p>
          </div>
        )}

        {watchlistTokens.length > 0 && (
          <>
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

            {/* Token rows */}
            <div className="space-y-1">
              {watchlistTokens.map((token) => (
                <div
                  key={token.mint}
                  onClick={() => token.geckoTerminalUrl && window.open(token.geckoTerminalUrl, "_blank", "noopener,noreferrer")}
                  className="grid cursor-pointer grid-cols-[2fr_1fr_1fr_1fr_1fr_auto_auto] items-center gap-3 rounded-lg px-2 py-2.5 transition-colors hover:bg-secondary/50"
                >
                  {/* Token info */}
                  <div className="flex items-center gap-2.5">
                    <div
                      className="flex h-8 w-8 items-center justify-center rounded-full text-[10px] font-bold text-white"
                      style={{ backgroundColor: token.color ?? "#9945FF" }}
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
                    {token.liquidity == null
                      ? "\u2014"
                      : token.liquidity >= 1_000_000
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

                  {/* External link */}
                  <span className="w-8 text-right text-muted-foreground">&uarr;</span>

                  {/* Unstar button */}
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      removeFromWatchlist(token.mint);
                    }}
                    className="flex w-8 items-center justify-center text-primary transition-colors hover:text-primary/70"
                  >
                    <Star className="h-4 w-4 fill-current" />
                  </button>
                </div>
              ))}
            </div>
          </>
        )}
      </div>
    </main>
  );
};

export default Watchlist;
