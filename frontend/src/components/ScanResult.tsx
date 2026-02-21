import { Shield, AlertTriangle, Loader2, Database, Brain, Users, Droplets, Clock, Lock, Snowflake, PieChart, TrendingUp } from "lucide-react";

interface ScanResultData {
  name: string;
  symbol: string;
  mint: string;
  riskScore: number;
  verdict: "SAFE" | "DANGER";
  metrics: {
    mlConfidence: number;
    holders: number;
    liquidity: number;
    poolAge: number;
    mintAuthority: boolean;
    freezeAuthority: boolean;
    rugCheckScore: number;
    topHolderPercent: number;
  };
  riskFactors: {
    level: "critical" | "high" | "medium";
    name: string;
    score: number;
    description: string;
  }[];
  aiAnalysis: string;
}

interface ScanResultProps {
  data: ScanResultData;
  loading: boolean;
}

const levelColors = {
  critical: "bg-danger/15 text-danger border-danger/30",
  high: "bg-warning/15 text-warning border-warning/30",
  medium: "bg-primary/15 text-primary border-primary/30",
};

const ScanResult = ({ data, loading }: ScanResultProps) => {
  if (loading) {
    return (
      <div className="mt-8 flex flex-col items-center justify-center gap-4 rounded-xl border border-border bg-card p-16">
        <Loader2 className="h-10 w-10 animate-spin text-primary" />
        <p className="text-sm text-muted-foreground">Running AI analysis on token...</p>
        <div className="animate-shimmer h-1 w-48 rounded-full" />
      </div>
    );
  }

  const isSafe = data.verdict === "SAFE";
  const glowClass = isSafe ? "glow-safe border-safe/40" : "glow-danger border-danger/40";

  return (
    <div className={`mt-8 animate-fade-in-up rounded-xl border bg-card p-6 ${glowClass}`}>
      {/* Header */}
      <div className="mb-6 flex items-center gap-5">
        <div
          className={`flex h-20 w-20 items-center justify-center rounded-2xl text-3xl font-black ${
            isSafe ? "bg-safe/15 text-safe" : "bg-danger/15 text-danger"
          }`}
        >
          {data.riskScore}%
        </div>
        <div>
          <div className="flex items-center gap-2">
            {isSafe ? <Shield className="h-5 w-5 text-safe" /> : <AlertTriangle className="h-5 w-5 text-danger" />}
            <span className={`text-xl font-bold ${isSafe ? "text-safe" : "text-danger"}`}>
              {data.verdict}
            </span>
          </div>
          <p className="text-lg font-semibold text-foreground">
            {data.name} ({data.symbol})
          </p>
          <p className="font-mono text-xs text-muted-foreground">
            {data.mint.slice(0, 12)}...{data.mint.slice(-8)}
          </p>
        </div>
      </div>

      {/* Risk meter */}
      <div className="mb-8">
        <div className="relative h-3 w-full overflow-hidden rounded-full">
          <div className="absolute inset-0 bg-gradient-to-r from-safe via-warning to-danger" />
          <div
            className="absolute top-1/2 h-5 w-5 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-foreground bg-foreground shadow-lg transition-all duration-700"
            style={{ left: `${data.riskScore}%` }}
          />
        </div>
        <div className="mt-1.5 flex justify-between text-[10px] text-muted-foreground">
          <span>Safe</span>
          <span>Moderate</span>
          <span>Dangerous</span>
        </div>
      </div>

      {/* Metrics grid */}
      <div className="mb-8 grid grid-cols-2 gap-3 md:grid-cols-4">
        {[
          { icon: Brain, label: "ML Confidence", value: `${data.metrics.mlConfidence}%` },
          { icon: Users, label: "Holders", value: data.metrics.holders.toLocaleString() },
          { icon: Droplets, label: "Liquidity", value: `$${data.metrics.liquidity >= 1e6 ? `${(data.metrics.liquidity / 1e6).toFixed(0)}M` : data.metrics.liquidity >= 1e3 ? `${(data.metrics.liquidity / 1e3).toFixed(1)}K` : data.metrics.liquidity}` },
          { icon: Clock, label: "Pool Age", value: `${data.metrics.poolAge} days` },
          { icon: Lock, label: "Mint Authority", value: data.metrics.mintAuthority ? "ENABLED ⚠️" : "Disabled ✓", danger: data.metrics.mintAuthority },
          { icon: Snowflake, label: "Freeze Authority", value: data.metrics.freezeAuthority ? "ENABLED ⚠️" : "Disabled ✓", danger: data.metrics.freezeAuthority },
          { icon: Database, label: "RugCheck Score", value: `${data.metrics.rugCheckScore}/100` },
          { icon: PieChart, label: "Top Holder %", value: `${data.metrics.topHolderPercent}%`, danger: data.metrics.topHolderPercent > 50 },
        ].map(({ icon: Icon, label, value, danger }, i) => (
          <div key={i} className="rounded-lg border border-border bg-secondary/50 p-3">
            <div className="flex items-center gap-1.5">
              <Icon className="h-3.5 w-3.5 text-muted-foreground" />
              <span className="text-[10px] uppercase tracking-wider text-muted-foreground">{label}</span>
            </div>
            <p className={`mt-1 text-sm font-bold ${danger ? "text-danger" : "text-foreground"}`}>{value}</p>
          </div>
        ))}
      </div>

      {/* Risk factors */}
      {data.riskFactors.length > 0 && (
        <div className="mb-8">
          <h3 className="mb-3 flex items-center gap-2 text-sm font-semibold text-foreground">
            <AlertTriangle className="h-4 w-4 text-danger" />
            Risk Factors
          </h3>
          <div className="space-y-2">
            {data.riskFactors.map((factor, i) => (
              <div key={i} className={`rounded-lg border p-3 ${levelColors[factor.level]}`}>
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <span className="rounded-md bg-current/10 px-1.5 py-0.5 text-[10px] font-bold uppercase">
                      {factor.level}
                    </span>
                    <span className="text-sm font-semibold">{factor.name}</span>
                  </div>
                  <span className="text-xs font-bold">+{factor.score} pts</span>
                </div>
                <p className="mt-1 text-xs opacity-80">{factor.description}</p>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* AI Analysis */}
      <div className="mb-6 rounded-lg border border-primary/20 bg-primary/5 p-4">
        <div className="mb-2 flex items-center gap-2">
          <Brain className="h-4 w-4 text-primary" />
          <h3 className="text-sm font-semibold text-primary">AI Analysis</h3>
        </div>
        <p className="text-sm leading-relaxed text-foreground/80">{data.aiAnalysis}</p>
      </div>

      {/* Data sources */}
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-[10px] text-muted-foreground">Data sources:</span>
        {["SolRPDS (116K events)", "RugCheck", "GeckoTerminal", "Helius"].map((s) => (
          <span key={s} className="rounded-full border border-border bg-secondary px-2 py-0.5 text-[10px] text-muted-foreground">
            {s}
          </span>
        ))}
      </div>
    </div>
  );
};

export default ScanResult;
