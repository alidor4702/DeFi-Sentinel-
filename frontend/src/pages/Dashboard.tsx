import { useEffect, useState } from "react";
import { BarChart3, ShieldAlert, Brain, Clock } from "lucide-react";
import StatCard from "@/components/StatCard";
import LivePoolMonitor from "@/components/LivePoolMonitor";
import RecentScans from "@/components/RecentScans";

const Dashboard = () => {
  const [stats, setStats] = useState({
    pools: 63521,
    rugs: 22555,
    accuracy: 94.2,
    scanned: 847,
  });

  // Slowly increment stats
  useEffect(() => {
    const interval = setInterval(() => {
      setStats((prev) => ({
        pools: prev.pools + Math.floor(Math.random() * 3),
        rugs: prev.rugs + (Math.random() > 0.7 ? 1 : 0),
        accuracy: 94.2,
        scanned: prev.scanned + Math.floor(Math.random() * 2),
      }));
    }, 5000);
    return () => clearInterval(interval);
  }, []);

  return (
    <div className="container py-6">
      {/* Stats row */}
      <div className="mb-6 grid grid-cols-2 gap-4 lg:grid-cols-4">
        <StatCard title="Pools Monitored" value={stats.pools} icon={BarChart3} variant="indigo" />
        <StatCard title="Rugs Detected" value={stats.rugs} suffix="(19.4%)" icon={ShieldAlert} variant="danger" />
        <StatCard title="ML Accuracy" value={stats.accuracy} icon={Brain} variant="safe" format="percent" />
        <StatCard title="Scanned 24h" value={stats.scanned} icon={Clock} variant="warning" />
      </div>

      {/* Main content */}
      <div className="grid gap-6 lg:grid-cols-[2fr_1fr]">
        <LivePoolMonitor />
        <RecentScans />
      </div>
    </div>
  );
};

export default Dashboard;
