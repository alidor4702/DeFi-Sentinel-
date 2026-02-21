import { useEffect, useState } from "react";
import { LucideIcon } from "lucide-react";

interface StatCardProps {
  title: string;
  value: number;
  suffix?: string;
  icon: LucideIcon;
  variant: "indigo" | "danger" | "safe" | "warning";
  format?: "number" | "percent";
}

const variantStyles = {
  indigo: "border-primary/30 bg-primary/5",
  danger: "border-danger/30 bg-danger/5",
  safe: "border-safe/30 bg-safe/5",
  warning: "border-warning/30 bg-warning/5",
};

const iconStyles = {
  indigo: "text-primary bg-primary/15",
  danger: "text-danger bg-danger/15",
  safe: "text-safe bg-safe/15",
  warning: "text-warning bg-warning/15",
};

const valueStyles = {
  indigo: "text-primary",
  danger: "text-danger",
  safe: "text-safe",
  warning: "text-warning",
};

const StatCard = ({ title, value, suffix, icon: Icon, variant, format = "number" }: StatCardProps) => {
  const [displayValue, setDisplayValue] = useState(0);

  useEffect(() => {
    const duration = 1500;
    const steps = 40;
    const increment = value / steps;
    let current = 0;
    const timer = setInterval(() => {
      current += increment;
      if (current >= value) {
        setDisplayValue(value);
        clearInterval(timer);
      } else {
        setDisplayValue(Math.floor(current));
      }
    }, duration / steps);
    return () => clearInterval(timer);
  }, [value]);

  const formatted = format === "percent"
    ? `${displayValue.toFixed(1)}%`
    : displayValue.toLocaleString();

  return (
    <div className={`rounded-xl border p-5 transition-all duration-300 hover:-translate-y-0.5 hover:shadow-lg ${variantStyles[variant]}`}>
      <div className="flex items-center justify-between">
        <p className="text-xs font-medium uppercase tracking-wider text-muted-foreground">{title}</p>
        <div className={`flex h-8 w-8 items-center justify-center rounded-lg ${iconStyles[variant]}`}>
          <Icon className="h-4 w-4" />
        </div>
      </div>
      <div className="mt-3 flex items-baseline gap-1.5">
        <span className={`text-2xl font-bold tabular-nums ${valueStyles[variant]}`}>
          {formatted}
        </span>
        {suffix && <span className="text-sm text-muted-foreground">{suffix}</span>}
      </div>
    </div>
  );
};

export default StatCard;
