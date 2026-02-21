import { Shield, Activity } from "lucide-react";
import { Link, useLocation } from "react-router-dom";

const navItems = [
  { label: "Dashboard", path: "/" },
  { label: "Scan Token", path: "/scan" },
];

const Header = () => {
  const location = useLocation();

  return (
    <header className="sticky top-0 z-50 border-b border-border bg-background/80 backdrop-blur-xl">
      <div className="container flex h-16 items-center justify-between">
        {/* Logo */}
        <Link to="/" className="flex items-center gap-2.5">
          <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-primary/20">
            <Shield className="h-5 w-5 text-primary" />
          </div>
          <div className="flex flex-col">
            <span className="text-sm font-bold leading-tight tracking-tight text-foreground">
              DeFi Sentinel
            </span>
            <span className="text-[10px] font-medium leading-tight text-muted-foreground">
              AI rug-pull detector
            </span>
          </div>
          <div className="ml-2 flex items-center gap-1.5 rounded-full border border-safe/30 bg-safe/10 px-2 py-0.5">
            <span className="relative flex h-2 w-2">
              <span className="absolute inline-flex h-full w-full animate-pulse-live rounded-full bg-safe opacity-75" />
              <span className="relative inline-flex h-2 w-2 rounded-full bg-safe" />
            </span>
            <span className="text-[10px] font-semibold uppercase tracking-wider text-safe">
              Live
            </span>
          </div>
        </Link>

        {/* Navigation */}
        <nav className="hidden items-center gap-1 md:flex">
          {navItems.map((item) => (
            <Link
              key={item.path}
              to={item.path}
              className={`rounded-lg px-3.5 py-2 text-sm font-medium transition-all duration-200 ${
                location.pathname === item.path
                  ? "bg-primary/15 text-primary"
                  : "text-muted-foreground hover:bg-secondary hover:text-foreground"
              }`}
            >
              {item.label}
            </Link>
          ))}
        </nav>

        {/* Solana Badge */}
        <div className="flex items-center gap-2">
          <div className="flex items-center gap-1.5 rounded-full border border-border bg-secondary px-3 py-1.5">
            <Activity className="h-3.5 w-3.5 text-primary" />
            <span className="text-xs font-semibold text-foreground">◎ Solana</span>
          </div>
        </div>
      </div>
    </header>
  );
};

export default Header;
