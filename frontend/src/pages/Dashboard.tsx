import { useEffect, useState, useCallback } from "react";
import { BarChart3, ShieldAlert, Shield, Database } from "lucide-react";
import StatCard from "@/components/StatCard";
import LivePoolMonitor from "@/components/LivePoolMonitor";
import { fetchTokens, TokenListItem } from "@/lib/api";

const Dashboard = () => {
  const [tokens, setTokens] = useState<TokenListItem[]>([]);

  const load = useCallback(async () => {
    try {
      const data = await fetchTokens();
      setTokens(data);
    } catch {
      // ignore
    }
  }, []);

  useEffect(() => {
    load();
    const interval = setInterval(load, 60_000);
    return () => clearInterval(interval);
  }, [load]);

  const poolCount = tokens.length;
  const rugCount = tokens.filter((t) => t.riskScore >= 70).length;
  const safeCount = tokens.filter((t) => t.riskScore < 40).length;
  const rugPct = poolCount > 0 ? ((rugCount / poolCount) * 100).toFixed(1) : "0.0";

  return (
    <div className="container py-6">
      {/* Stats row */}
      <div className="mb-6 grid grid-cols-2 gap-4 lg:grid-cols-4">
        <StatCard title="Pools Monitored" value={poolCount} icon={BarChart3} variant="indigo" />
        <StatCard title="Rugs Detected" value={rugCount} suffix={`(${rugPct}%)`} icon={ShieldAlert} variant="danger" />
        <StatCard title="Safe Tokens" value={safeCount} icon={Shield} variant="safe" />
        <StatCard title="Data Sources" value={5} icon={Database} variant="warning" />
      </div>

      {/* Two-table monitor — full width grid handled inside component */}
      <LivePoolMonitor />
    </div>
  );
};

export default Dashboard;
