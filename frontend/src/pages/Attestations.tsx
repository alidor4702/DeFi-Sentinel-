import { useState, useEffect } from "react";
import { FileCheck2, ExternalLink, Link2, RefreshCw, Shield, AlertTriangle, Loader2, Search } from "lucide-react";
import { fetchAttestations, AttestationRecord } from "@/lib/solana";
import { Link } from "react-router-dom";

const Attestations = () => {
  const [records, setRecords] = useState<AttestationRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [filter, setFilter] = useState("");

  const load = async () => {
    setLoading(true);
    setError("");
    try {
      const data = await fetchAttestations();
      setRecords(data);
    } catch (e: any) {
      setError(e.message || "Failed to load attestations");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, []);

  const filtered = filter
    ? records.filter(
        (r) =>
          r.mint.toLowerCase().includes(filter.toLowerCase()) ||
          r.txSignature.toLowerCase().includes(filter.toLowerCase()) ||
          r.verdict.toLowerCase().includes(filter.toLowerCase()),
      )
    : records;

  return (
    <div className="container py-8">
      {/* Page header */}
      <div className="mb-8 flex items-start justify-between">
        <div>
          <div className="flex items-center gap-3 mb-2">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-primary/20">
              <FileCheck2 className="h-5 w-5 text-primary" />
            </div>
            <div>
              <h1 className="text-2xl font-bold text-foreground">On-chain Attestations</h1>
              <p className="text-sm text-muted-foreground">
                Immutable risk assessments recorded on Solana
              </p>
            </div>
          </div>
        </div>
        <button
          onClick={load}
          disabled={loading}
          className="flex items-center gap-2 rounded-lg border border-border bg-secondary px-3 py-2 text-xs font-medium text-foreground transition-colors hover:bg-secondary/80 disabled:opacity-50"
        >
          <RefreshCw className={`h-3.5 w-3.5 ${loading ? "animate-spin" : ""}`} />
          Refresh
        </button>
      </div>

      {/* Stats bar */}
      <div className="mb-6 grid grid-cols-2 gap-3 md:grid-cols-4">
        <div className="rounded-lg border border-border bg-card p-4">
          <span className="text-[10px] uppercase tracking-wider text-muted-foreground">Total Attestations</span>
          <p className="mt-1 text-2xl font-bold text-foreground">{records.length}</p>
        </div>
        <div className="rounded-lg border border-safe/30 bg-safe/5 p-4">
          <span className="text-[10px] uppercase tracking-wider text-muted-foreground">Safe Tokens</span>
          <p className="mt-1 text-2xl font-bold text-safe">
            {records.filter((r) => r.verdict === "SAFE").length}
          </p>
        </div>
        <div className="rounded-lg border border-danger/30 bg-danger/5 p-4">
          <span className="text-[10px] uppercase tracking-wider text-muted-foreground">Danger Tokens</span>
          <p className="mt-1 text-2xl font-bold text-danger">
            {records.filter((r) => r.verdict === "DANGER").length}
          </p>
        </div>
        <div className="rounded-lg border border-primary/30 bg-primary/5 p-4">
          <span className="text-[10px] uppercase tracking-wider text-muted-foreground">Network</span>
          <p className="mt-1 text-2xl font-bold text-primary">Devnet</p>
        </div>
      </div>

      {/* Search */}
      <div className="mb-4 relative">
        <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
        <input
          type="text"
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          placeholder="Search by mint address, tx signature, or verdict..."
          className="h-10 w-full rounded-lg border border-border bg-card pl-10 pr-4 text-sm text-foreground placeholder:text-muted-foreground focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
        />
      </div>

      {/* Error */}
      {error && (
        <div className="mb-4 rounded-lg bg-danger/10 px-4 py-3 text-sm text-danger">{error}</div>
      )}

      {/* Loading */}
      {loading && records.length === 0 && (
        <div className="flex flex-col items-center justify-center gap-4 py-20">
          <Loader2 className="h-8 w-8 animate-spin text-primary" />
          <p className="text-sm text-muted-foreground">Loading attestation history...</p>
        </div>
      )}

      {/* Empty state */}
      {!loading && records.length === 0 && (
        <div className="flex flex-col items-center justify-center gap-4 rounded-xl border border-border bg-card py-20">
          <FileCheck2 className="h-12 w-12 text-muted-foreground/30" />
          <div className="text-center">
            <p className="text-lg font-semibold text-foreground">No attestations yet</p>
            <p className="mt-1 text-sm text-muted-foreground">
              Scan a token and click "Attest on Solana" to create your first on-chain record.
            </p>
          </div>
          <Link
            to="/scan"
            className="mt-2 rounded-lg bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground transition-all hover:opacity-90"
          >
            Scan a Token
          </Link>
        </div>
      )}

      {/* Attestation records */}
      {filtered.length > 0 && (
        <div className="space-y-3">
          {filtered.map((record) => {
            const isSafe = record.verdict === "SAFE";
            const isSimulated = record.txSignature.startsWith("sim_");

            return (
              <div
                key={record.id}
                className={`rounded-xl border bg-card p-4 transition-colors hover:bg-card/80 ${
                  isSafe ? "border-safe/20" : "border-danger/20"
                }`}
              >
                <div className="flex items-start justify-between gap-4">
                  {/* Left: token info */}
                  <div className="flex items-center gap-3 min-w-0">
                    <div
                      className={`flex h-12 w-12 shrink-0 items-center justify-center rounded-xl text-lg font-black ${
                        isSafe ? "bg-safe/15 text-safe" : "bg-danger/15 text-danger"
                      }`}
                    >
                      {record.riskScore}%
                    </div>
                    <div className="min-w-0">
                      <div className="flex items-center gap-2">
                        {isSafe ? (
                          <Shield className="h-4 w-4 text-safe" />
                        ) : (
                          <AlertTriangle className="h-4 w-4 text-danger" />
                        )}
                        <span className={`text-sm font-bold ${isSafe ? "text-safe" : "text-danger"}`}>
                          {record.verdict}
                        </span>
                        {isSimulated && (
                          <span className="rounded-full bg-warning/10 px-2 py-0.5 text-[9px] font-bold text-warning">
                            SIMULATED
                          </span>
                        )}
                      </div>
                      <Link
                        to={`/scan/${record.mint}`}
                        className="font-mono text-xs text-muted-foreground hover:text-primary transition-colors"
                      >
                        {record.mint.slice(0, 16)}...{record.mint.slice(-8)}
                      </Link>
                    </div>
                  </div>

                  {/* Right: attestation details */}
                  <div className="shrink-0 text-right space-y-1">
                    <p className="text-xs text-muted-foreground">
                      {new Date(record.attestedAt).toLocaleDateString()}{" "}
                      {new Date(record.attestedAt).toLocaleTimeString()}
                    </p>
                    <p className="font-mono text-[10px] text-muted-foreground">
                      Hash: {record.featuresHash.slice(0, 12)}...
                    </p>
                  </div>
                </div>

                {/* Transaction links */}
                <div className="mt-3 flex items-center gap-2 border-t border-border pt-3">
                  <span className="text-[10px] text-muted-foreground mr-1">TX:</span>
                  <span className="font-mono text-[10px] text-foreground">
                    {record.txSignature.slice(0, 20)}...
                  </span>
                  <div className="ml-auto flex gap-2">
                    {!isSimulated && (
                      <>
                        <a
                          href={record.explorerUrl}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="inline-flex items-center gap-1 rounded-md border border-primary/30 bg-primary/10 px-2 py-1 text-[10px] font-medium text-primary hover:bg-primary/20 transition-colors"
                        >
                          <Link2 className="h-2.5 w-2.5" />
                          Explorer
                        </a>
                        <a
                          href={record.solscanUrl}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="inline-flex items-center gap-1 rounded-md border border-border bg-secondary px-2 py-1 text-[10px] font-medium text-foreground hover:bg-secondary/80 transition-colors"
                        >
                          <ExternalLink className="h-2.5 w-2.5" />
                          Solscan
                        </a>
                      </>
                    )}
                    <Link
                      to={`/scan/${record.mint}`}
                      className="inline-flex items-center gap-1 rounded-md border border-border bg-secondary px-2 py-1 text-[10px] font-medium text-foreground hover:bg-secondary/80 transition-colors"
                    >
                      Re-scan
                    </Link>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Info footer */}
      <div className="mt-8 rounded-lg border border-primary/10 bg-primary/5 p-4">
        <div className="flex items-start gap-3">
          <FileCheck2 className="h-5 w-5 text-primary shrink-0 mt-0.5" />
          <div>
            <h4 className="text-sm font-semibold text-foreground">How On-chain Attestation Works</h4>
            <p className="mt-1 text-xs text-muted-foreground leading-relaxed">
              When you attest a risk scan, DeFi Sentinel creates a SHA-256 hash of the scan results
              (token mint, risk score, verdict, and timestamp) and writes it to the Solana blockchain
              using the Memo program. This creates an immutable, publicly verifiable record that
              proves the scan result existed at a specific point in time. Anyone can independently
              verify the attestation by checking the transaction on Solana Explorer.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
};

export default Attestations;
