import { useState } from "react";
import { Search, Shield } from "lucide-react";
import ScanResult from "@/components/ScanResult";
import { SAFE_TOKEN_RESULT, DANGER_TOKEN_RESULT } from "@/data/mockData";

const USDC_MINT = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v";

const ScanToken = () => {
  const [address, setAddress] = useState("");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<typeof SAFE_TOKEN_RESULT | typeof DANGER_TOKEN_RESULT | null>(null);

  const handleScan = () => {
    if (!address.trim()) return;
    setLoading(true);
    setResult(null);
    setTimeout(() => {
      setResult(address.trim() === USDC_MINT ? SAFE_TOKEN_RESULT : DANGER_TOKEN_RESULT);
      setLoading(false);
    }, 2000);
  };

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
          disabled={!address.trim() || scansRemaining <= 0}
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

      {/* Results */}
      {(loading || result) && (
        <ScanResult data={result || DANGER_TOKEN_RESULT} loading={loading} />
      )}
    </div>
  );
};

export default ScanToken;
