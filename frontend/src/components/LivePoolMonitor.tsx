import { useEffect, useState, useCallback, useMemo, useRef } from "react";
import { useNavigate } from "react-router-dom";
import { Activity, Loader2, RefreshCw, Star, SlidersHorizontal, ExternalLink, DollarSign, ShieldAlert } from "lucide-react";
import { fetchTokens, refreshTokens, fetchFilteredTokens, TokenListItem } from "@/lib/api";
import { useWatchlist } from "@/context/WatchlistContext";

const POLL_INTERVAL = 60_000;

/* ── helpers ─────────────────────────────────────────────── */

function formatAge(hours: number | null): string {
  if (hours === null || hours === undefined) return "—";
  if (hours < 1) return `${Math.max(1, Math.round(hours * 60))}m`;
  if (hours < 24) return `${Math.round(hours)}h`;
  if (hours < 168) return `${Math.round(hours / 24)}d`;
  return `${Math.round(hours / 168)}w`;
}

function formatLiquidity(liq: number) {
  if (liq >= 1_000_000) return `$${(liq / 1_000_000).toFixed(1)}M`;
  if (liq >= 1_000) return `$${(liq / 1_000).toFixed(1)}K`;
  return `$${liq.toFixed(0)}`;
}

function riskBarColor(score: number) {
  if (score >= 70) return "hsl(0 84% 60%)";
  if (score >= 40) return "hsl(38 92% 50%)";
  return "hsl(160 84% 39%)";
}

function verdictBadge(score: number) {
  if (score >= 70)
    return { cls: "bg-danger/15 text-danger", label: `${score}% RUG` };
  if (score >= 40)
    return { cls: "bg-amber-500/15 text-amber-500", label: `${score}% MODERATE` };
  return { cls: "bg-safe/15 text-safe", label: `${score}% SAFE` };
}

/* ── single token row (click → scan page, ext link separate) */

function TokenRow({ token }: { token: TokenListItem }) {
  const navigate = useNavigate();
  const { addToWatchlist, removeFromWatchlist, isInWatchlist } = useWatchlist();
  const starred = isInWatchlist(token.mint);
  const badge = verdictBadge(token.riskScore);

  return (
    <div
      onClick={() => navigate(`/scan/${token.mint}`)}
      className="animate-slide-in-bottom grid cursor-pointer grid-cols-[2fr_1fr_1fr_1fr_1fr_auto_auto] items-center gap-3 rounded-lg px-2 py-2 transition-colors hover:bg-secondary/50"
    >
      {/* Token info */}
      <div className="flex items-center gap-2.5">
        <div
          className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-[10px] font-bold text-white"
          style={{ backgroundColor: token.color }}
        >
          {token.symbol.slice(0, 2)}
        </div>
        <div className="min-w-0">
          <p className="truncate text-sm font-medium text-foreground">{token.name}</p>
          <p className="font-mono text-[10px] text-muted-foreground">
            {token.mint.slice(0, 4)}…{token.mint.slice(-4)}
          </p>
        </div>
      </div>

      {/* Liquidity */}
      <span className="text-xs tabular-nums text-foreground">
        {formatLiquidity(token.liquidity)}
      </span>

      {/* Risk bar */}
      <div className="flex items-center gap-2">
        <div className="h-1.5 w-full max-w-[60px] overflow-hidden rounded-full bg-secondary">
          <div
            className="h-full rounded-full transition-all duration-500"
            style={{ width: `${token.riskScore}%`, backgroundColor: riskBarColor(token.riskScore) }}
          />
        </div>
      </div>

      {/* Verdict badge */}
      <span className={`inline-flex w-fit items-center rounded-full px-2 py-0.5 text-[10px] font-bold ${badge.cls}`}>
        {badge.label}
      </span>

      {/* Launched */}
      <span className="text-xs tabular-nums text-muted-foreground">
        {formatAge(token.poolAgeHours)}
      </span>

      {/* External link */}
      <button
        onClick={(e) => {
          e.stopPropagation();
          window.open(token.geckoTerminalUrl, "_blank", "noopener,noreferrer");
        }}
        className="flex w-8 items-center justify-center text-muted-foreground transition-colors hover:text-primary"
        title="Open on GeckoTerminal"
      >
        <ExternalLink className="h-3.5 w-3.5" />
      </button>

      {/* Star */}
      <button
        onClick={(e) => {
          e.stopPropagation();
          starred
            ? removeFromWatchlist(token.mint)
            : addToWatchlist({
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
        }}
        className={`flex w-8 items-center justify-center transition-colors ${
          starred ? "text-primary hover:text-primary/70" : "text-muted-foreground hover:text-primary"
        }`}
        title={starred ? "Remove from watchlist" : "Add to watchlist"}
      >
        <Star className={`h-4 w-4 ${starred ? "fill-current" : ""}`} />
      </button>
    </div>
  );
}

/* ── column header ───────────────────────────────────────── */

function ColHeader() {
  return (
    <div className="mb-1 grid grid-cols-[2fr_1fr_1fr_1fr_1fr_auto_auto] gap-3 border-b border-border px-2 pb-2 text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
      <span>Token</span>
      <span>Liquidity</span>
      <span>Risk</span>
      <span>Verdict</span>
      <span>Launched</span>
      <span className="w-8" />
      <span className="w-8" />
    </div>
  );
}

/* ── placeholder ─────────────────────────────────────────── */

function Placeholder({ text }: { text: string }) {
  return (
    <div className="flex flex-col items-center justify-center py-10 text-center">
      <Loader2 className="h-5 w-5 animate-spin text-primary" />
      <span className="mt-2 text-xs text-muted-foreground">{text}</span>
    </div>
  );
}

/* ═══════════════════════════════════════════════════════════
   MAIN COMPONENT
   ═══════════════════════════════════════════════════════════ */

const LivePoolMonitor = () => {
  const [tokens, setTokens] = useState<TokenListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState(false);

  // Risk Scanner state
  const [riskThreshold, setRiskThreshold] = useState(100);
  const [filterMode, setFilterMode] = useState<"risk" | "liquidity">("risk");
  const [filteredTokens, setFilteredTokens] = useState<TokenListItem[]>([]);
  const [filterLoading, setFilterLoading] = useState(false);
  const [filterScanning, setFilterScanning] = useState(false);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  /* ── Live Feed data fetching ───────────────────────────── */

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
      await refreshTokens();
    } catch { /* silent */ }
    // Poll quickly for a few seconds to pick up new results
    let polls = 0;
    const poller = setInterval(async () => {
      polls++;
      try {
        const data = await fetchTokens();
        setTokens(data);
      } catch { /* ignore */ }
      if (polls >= 6) clearInterval(poller);
    }, 3_000);
    setTimeout(() => setRefreshing(false), 3_000);
  }, []);

  useEffect(() => { load(); }, [load]);

  useEffect(() => {
    const delay = tokens.length === 0 ? 5_000 : POLL_INTERVAL;
    const id = setInterval(load, delay);
    return () => clearInterval(id);
  }, [load, tokens.length]);

  /* WebSocket for real-time pushes */
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
            setTokens((prev) => [msg.data, ...prev]);
          }
        } catch { /* ignore */ }
      };
    } catch { /* WS not available */ }
    return () => { try { ws?.close(); } catch {} };
  }, []);

  /* ── Risk Scanner: call /api/tokens/filter on slider change */

  const fetchFiltered = useCallback(async (maxRisk: number, sort: "risk" | "liquidity") => {
    setFilterLoading(true);
    try {
      const resp = await fetchFilteredTokens({ maxRisk, sort, limit: 10 });
      setFilteredTokens(resp.tokens);
      setFilterScanning(resp.scanning);

      // If backend is scanning for more, poll a few times to get results
      if (resp.scanning && resp.tokens.length < 5) {
        let attempts = 0;
        const poller = setInterval(async () => {
          attempts++;
          try {
            const r2 = await fetchFilteredTokens({ maxRisk, sort, limit: 10 });
            setFilteredTokens(r2.tokens);
            setFilterScanning(r2.scanning);
            if (r2.tokens.length >= 5 || !r2.scanning || attempts >= 8) {
              clearInterval(poller);
              setFilterScanning(false);
            }
          } catch { /* ignore */ }
        }, 4_000);
      }
    } catch { /* silent */ }
    setFilterLoading(false);
  }, []);

  // Debounced slider change
  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => {
      fetchFiltered(riskThreshold, filterMode);
    }, 300);
    return () => { if (debounceRef.current) clearTimeout(debounceRef.current); };
  }, [riskThreshold, filterMode, fetchFiltered]);

  // Initial filter load
  useEffect(() => {
    fetchFiltered(100, "risk");
  }, [fetchFiltered]);

  /* ── Live Feed: newest first ───────────────────────────── */

  const liveFeed = useMemo(
    () =>
      [...tokens]
        .sort((a, b) => (a.poolAgeHours ?? 999_999) - (b.poolAgeHours ?? 999_999))
        .slice(0, 10),
    [tokens],
  );

  /* ── slider color ──────────────────────────────────────── */
  const sliderColor =
    riskThreshold >= 70
      ? "hsl(0 84% 60%)"
      : riskThreshold >= 40
      ? "hsl(38 92% 50%)"
      : "hsl(160 84% 39%)";

  /* ── render ────────────────────────────────────────────── */

  return (
    <div className="grid gap-5 lg:grid-cols-2">
      {/* ───────── TABLE 1 : LIVE FEED ───────── */}
      <div className="rounded-xl border border-border bg-card p-5">
        <div className="mb-3 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Activity className="h-4 w-4 text-primary" />
            <h2 className="text-sm font-semibold text-foreground">Live Feed</h2>
          </div>

          <span className="flex items-center gap-1.5 text-xs text-muted-foreground">
            <span className="relative flex h-1.5 w-1.5">
              <span className="absolute inline-flex h-full w-full animate-pulse-live rounded-full bg-safe" />
              <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-safe" />
            </span>
            {loading ? "Loading…" : "Live"}
          </span>

          <button
            onClick={handleRefresh}
            disabled={refreshing}
            className="rounded-md p-1 text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground disabled:opacity-50"
            title="Refresh — fetch fresh tokens"
          >
            <RefreshCw className={`h-3.5 w-3.5 ${refreshing ? "animate-spin" : ""}`} />
          </button>
        </div>

        <p className="mb-3 text-[10px] text-muted-foreground">
          Latest tokens — click to scan, <ExternalLink className="inline h-2.5 w-2.5" /> for chart
        </p>

        <ColHeader />

        {loading && tokens.length === 0 && <Placeholder text="Discovering tokens…" />}
        {!loading && tokens.length === 0 && (
          <Placeholder text={error ? "Backend unavailable — retrying…" : "Waiting for first scans…"} />
        )}

        <div className="space-y-0.5">
          {liveFeed.map((t) => (
            <TokenRow key={t.id} token={t} />
          ))}
        </div>
      </div>

      {/* ───────── TABLE 2 : RISK SCANNER ───────── */}
      <div className="rounded-xl border border-border bg-card p-5">
        {/* header + mode toggle */}
        <div className="mb-3 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <SlidersHorizontal className="h-4 w-4 text-danger" />
            <h2 className="text-sm font-semibold text-foreground">Risk Scanner</h2>
          </div>

          {/* Filter mode toggle */}
          <div className="flex items-center gap-1 rounded-lg border border-border p-0.5 text-[10px]">
            <button
              onClick={() => setFilterMode("risk")}
              className={`rounded-md px-2 py-1 font-medium transition-colors ${
                filterMode === "risk"
                  ? "bg-danger/20 text-danger"
                  : "text-muted-foreground hover:text-foreground"
              }`}
              title="Sort by risk (newest first)"
            >
              <ShieldAlert className="mr-1 inline h-3 w-3" />Risk
            </button>
            <button
              onClick={() => setFilterMode("liquidity")}
              className={`rounded-md px-2 py-1 font-medium transition-colors ${
                filterMode === "liquidity"
                  ? "bg-primary/20 text-primary"
                  : "text-muted-foreground hover:text-foreground"
              }`}
              title="Sort by highest liquidity"
            >
              <DollarSign className="mr-1 inline h-3 w-3" />Liquidity
            </button>
          </div>

          <span className="text-xs tabular-nums font-semibold" style={{ color: sliderColor }}>
            ≤ {riskThreshold}%
          </span>
        </div>

        {/* slider */}
        <div className="mb-4">
          <label className="mb-1.5 flex items-center justify-between text-[10px] text-muted-foreground">
            <span>Max&nbsp;Risk&nbsp;Threshold</span>
            <span className="tabular-nums font-medium" style={{ color: sliderColor }}>
              Show tokens ≤ {riskThreshold}%
            </span>
          </label>

          <input
            type="range"
            min={0}
            max={100}
            step={1}
            value={riskThreshold}
            onChange={(e) => setRiskThreshold(Number(e.target.value))}
            className="risk-slider w-full"
            title={`Risk threshold: ${riskThreshold}%`}
            style={{ "--slider-color": sliderColor } as React.CSSProperties}
          />

          <div className="mt-1.5 flex justify-between text-[9px] text-muted-foreground/60">
            <span>0 %&nbsp;(safe only)</span>
            <span className="text-amber-500/60">40 %</span>
            <span className="text-danger/60">70 %</span>
            <span>100 %&nbsp;(all)</span>
          </div>
        </div>

        <ColHeader />

        {filterLoading && filteredTokens.length === 0 && <Placeholder text="Searching…" />}

        {filterScanning && filteredTokens.length < 5 && (
          <div className="mb-2 flex items-center gap-2 rounded-lg bg-primary/5 px-3 py-2 text-[10px] text-primary">
            <Loader2 className="h-3 w-3 animate-spin" />
            Scanning more tokens to find matches…
          </div>
        )}

        {!filterLoading && filteredTokens.length === 0 && (
          <div className="py-10 text-center text-xs text-muted-foreground">
            No tokens with risk ≤ {riskThreshold}% yet — scanning for more…
          </div>
        )}

        <div className="space-y-0.5">
          {filteredTokens.map((t) => (
            <TokenRow key={t.id} token={t} />
          ))}
        </div>
      </div>
    </div>
  );
};

export default LivePoolMonitor;
