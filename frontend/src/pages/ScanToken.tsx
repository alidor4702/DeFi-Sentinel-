import { useState, useEffect } from "react";
import { useParams } from "react-router-dom";
import { Search, Shield } from "lucide-react";
import ScanResult from "@/components/ScanResult";
import { scanToken, ScanResultData } from "@/lib/api";

const USDC_MINT = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v";

const ScanToken = () => {
  const { mint: urlMint } = useParams<{ mint?: string }>();
  const [address, setAddress] = useState(urlMint || "");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<ScanResultData | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleScan = async (mintOverride?: string) => {
    const mint = (mintOverride || address).trim();
    if (!mint) return;
    setAddress(mint);
    setLoading(true);
    setResult(null);
    setError(null);
    try {
      const data = await scanToken(mint);
      setResult(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Scan failed");
    } finally {
      setLoading(false);
    }
  };

  // Auto-scan when navigating from dashboard token click
  useEffect(() => {
    if (urlMint && urlMint.length >= 32) {
      handleScan(urlMint);
    }
  }, [urlMint]); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div className="container max-w-3xl py-12">
      <div className="mb-8 text-center">
        <h1 className="text-3xl font-bold text-foreground">Scan a Token</h1>
        <p className="mt-2 text-muted-foreground">Paste a Solana mint address to get an instant AI risk analysis</p>
      </div>

      {/* Search */}
      <div className="flex gap-2">
        <div className="relative flex-1">
          <Search className="absolute left-4 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <input
            value={address}
            onChange={(e) => setAddress(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleScan()}
            placeholder="Enter Solana token mint address"
            className="h-12 w-full rounded-xl border border-border bg-card pl-11 pr-4 text-sm text-foreground placeholder:text-muted-foreground focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
          />
        </div>
        <button
          onClick={handleScan}
          disabled={!address.trim() || loading}
          className="flex h-12 items-center gap-2 rounded-xl bg-primary px-6 text-sm font-semibold text-primary-foreground transition-all hover:opacity-90 disabled:opacity-40"
        >
          <Shield className="h-4 w-4" />
          Analyze
        </button>
      </div>

      {/* Quick fill */}
      <div className="mt-3 flex items-center gap-2 text-xs text-muted-foreground">
        <span>Try:</span>
        <button
          onClick={() => setAddress(USDC_MINT)}
          className="rounded-md bg-safe/10 px-2 py-0.5 text-safe transition-colors hover:bg-safe/20"
        >
          USDC (safe)
        </button>
        <button
          onClick={() => setAddress("7xKXtg2CW87d97TXJSDpbD5jBkheTqA83TZRuJosgAsU")}
          className="rounded-md bg-danger/10 px-2 py-0.5 text-danger transition-colors hover:bg-danger/20"
        >
          suspicious token
        </button>
      </div>

      {/* Error */}
      {error && (
        <div className="mt-6 rounded-xl border border-danger/30 bg-danger/10 p-4 text-sm text-danger">
          {error}
        </div>
      )}

      {/* Results */}
      {(loading || result) && (
        <ScanResult data={result} loading={loading} />
      )}
    </div>
  );
};

export default ScanToken;
