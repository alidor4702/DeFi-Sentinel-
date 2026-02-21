import { useEffect, useState, useCallback } from "react";
import { BarChart3, ShieldAlert, Brain, Clock } from "lucide-react";
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
  const rugCount = tokens.filter((t) => t.riskScore > 50).length;
  const rugPct = poolCount > 0 ? ((rugCount / poolCount) * 100).toFixed(1) : "0.0";

  return (
    <div className="container py-6">
      {/* Stats row */}
      <div className="mb-6 grid grid-cols-2 gap-4 lg:grid-cols-4">
        <StatCard title="Pools Monitored" value={poolCount} icon={BarChart3} variant="indigo" />
        <StatCard title="Rugs Detected" value={rugCount} suffix={`(${rugPct}%)`} icon={ShieldAlert} variant="danger" />
        <StatCard title="ML Model AUC" value={99.95} icon={Brain} variant="safe" format="percent" />
        <StatCard title="Features per Scan" value={81} icon={Clock} variant="warning" />
      </div>

      {/* Main content — full width now */}
      <LivePoolMonitor />
    </div>
  );
};

export default Dashboard;
