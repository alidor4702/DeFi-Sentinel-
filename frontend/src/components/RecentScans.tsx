import { Shield, AlertTriangle } from "lucide-react";
import { COMMUNITY_SCANS } from "@/data/mockData";

const RecentScans = () => {
  return (
    <div className="rounded-xl border border-border bg-card p-5">
      <h2 className="mb-4 text-sm font-semibold text-foreground">Recent Community Scans</h2>
      <div className="space-y-2">
        {COMMUNITY_SCANS.map((scan, i) => (
          <div
            key={i}
            className="flex items-center justify-between rounded-lg px-3 py-2.5 transition-colors hover:bg-secondary/50"
          >
            <div className="flex items-center gap-2.5">
              {scan.safe ? (
                <Shield className="h-4 w-4 text-safe" />
              ) : (
                <AlertTriangle className="h-4 w-4 text-danger" />
              )}
              <span className="text-sm font-medium text-foreground">{scan.name}</span>
            </div>
            <div className="flex items-center gap-3">
              <span
                className={`text-xs font-bold tabular-nums ${
                  scan.safe ? "text-safe" : "text-danger"
                }`}
              >
                {scan.riskScore}%
              </span>
              <span className="text-[10px] text-muted-foreground">{scan.time}</span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};

export default RecentScans;
