import { useState } from "react";
import { Check, Shield, CreditCard, Lock, X, Loader2 } from "lucide-react";

const tiers = [
  {
    name: "Free",
    price: 0,
    period: "forever",
    description: "Start scanning tokens today",
    badge: null,
    variant: "default" as const,
    plan: null,
    features: ["3 scans/day", "Basic risk score", "Delayed live feed", "Community support"],
    excluded: ["Full 46-feature breakdown", "Real-time alerts", "API access", "AI explanation"],
    cta: "Current Plan",
  },
  {
    name: "Pro",
    price: 29,
    period: "/month",
    description: "For active traders & researchers",
    badge: "MOST POPULAR",
    variant: "popular" as const,
    plan: "pro",
    features: [
      "Unlimited scans",
      "Full 46-feature breakdown",
      "Real-time Telegram/Discord alerts",
      "API access (1,000 req/day)",
      "Historical analysis",
      "AI explanation",
      "Priority support",
    ],
    excluded: [],
    cta: "Subscribe with Stripe",
  },
  {
    name: "Enterprise",
    price: 499,
    period: "/month",
    description: "For wallets, DEXs & platforms",
    badge: "FOR WALLETS & DEXS",
    variant: "enterprise" as const,
    plan: "enterprise",
    features: [
      "Everything in Pro",
      "Unlimited API",
      "White-label widget",
      "Stripe Agent Toolkit integration",
      "Webhook alerts",
      "Custom ML training",
      "SLA guarantee",
    ],
    excluded: [],
    cta: "Subscribe with Stripe",
  },
];

const scanPacks = [
  { scans: 10, price: 1.99, badge: null, plan: "pack-10" },
  { scans: 50, price: 7.99, badge: "BEST VALUE", plan: "pack-50" },
  { scans: 200, price: 24.99, badge: null, plan: "pack-200" },
];

const Pricing = () => {
  const [loadingPlan, setLoadingPlan] = useState<string | null>(null);

  const tierStyles = {
    default: "border-border bg-card",
    popular: "border-primary/50 bg-card glow-indigo relative",
    enterprise: "border-border bg-card",
  };

  const ctaStyles = {
    default: "bg-secondary text-secondary-foreground hover:bg-secondary/80",
    popular: "bg-primary text-primary-foreground hover:opacity-90",
    enterprise: "bg-primary/80 text-primary-foreground hover:opacity-90",
  };

  const handleCheckout = async (plan: string) => {
    setLoadingPlan(plan);
    try {
      const res = await fetch("/api/create-checkout", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ plan }),
      });
      if (!res.ok) throw new Error(await res.text());
      const data = await res.json();
      if (data?.url) {
        window.open(data.url, "_blank");
      }
    } catch (err) {
      console.error("Checkout error:", err);
    } finally {
      setLoadingPlan(null);
    }
  };

  return (
    <div className="container max-w-6xl py-12">
      <div className="mb-10 text-center">
        <h1 className="text-3xl font-bold text-foreground">Protect Your Portfolio</h1>
        <p className="mt-2 text-muted-foreground">Choose a plan that fits your trading strategy</p>
      </div>

      {/* Tiers */}
      <div className="mb-16 grid gap-6 md:grid-cols-3">
        {tiers.map((tier) => (
          <div
            key={tier.name}
            className={`rounded-xl border p-6 transition-all duration-300 hover:-translate-y-1 ${tierStyles[tier.variant]}`}
          >
            {tier.badge && (
              <span className="mb-4 inline-block rounded-full bg-primary/15 px-3 py-1 text-[10px] font-bold uppercase tracking-wider text-primary">
                {tier.badge}
              </span>
            )}
            <h3 className="text-lg font-bold text-foreground">{tier.name}</h3>
            <p className="mt-1 text-xs text-muted-foreground">{tier.description}</p>
            <div className="mt-4 flex items-baseline gap-1">
              <span className="text-4xl font-black text-foreground">${tier.price}</span>
              <span className="text-sm text-muted-foreground">{tier.period}</span>
            </div>

            <button
              onClick={() => tier.plan && handleCheckout(tier.plan)}
              disabled={!tier.plan || loadingPlan === tier.plan}
              className={`mt-6 flex w-full items-center justify-center gap-2 rounded-lg py-2.5 text-sm font-semibold transition-all disabled:opacity-60 ${ctaStyles[tier.variant]}`}
            >
              {loadingPlan === tier.plan ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                tier.cta
              )}
            </button>

            {tier.plan && (
              <p className="mt-2 text-center text-[10px] text-muted-foreground">7-day free trial included</p>
            )}

            <div className="mt-6 space-y-2.5">
              {tier.features.map((f) => (
                <div key={f} className="flex items-center gap-2 text-sm text-foreground">
                  <Check className="h-3.5 w-3.5 text-safe" />
                  {f}
                </div>
              ))}
              {tier.excluded.map((f) => (
                <div key={f} className="flex items-center gap-2 text-sm text-muted-foreground/50">
                  <X className="h-3.5 w-3.5" />
                  {f}
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>

      {/* Pay-per-scan */}
      <div className="mb-16">
        <h2 className="mb-6 text-center text-xl font-bold text-foreground">Pay-Per-Scan Packs</h2>
        <div className="grid gap-4 md:grid-cols-3">
          {scanPacks.map((pack) => (
            <div key={pack.scans} className="rounded-xl border border-border bg-card p-5 text-center transition-all hover:-translate-y-0.5">
              {pack.badge && (
                <span className="mb-2 inline-block rounded-full bg-safe/15 px-2.5 py-0.5 text-[10px] font-bold text-safe">
                  {pack.badge}
                </span>
              )}
              <p className="text-3xl font-black text-foreground">{pack.scans}</p>
              <p className="text-xs text-muted-foreground">scans</p>
              <p className="mt-2 text-xl font-bold text-primary">${pack.price}</p>
              <button
                onClick={() => handleCheckout(pack.plan)}
                disabled={loadingPlan === pack.plan}
                className="mt-4 flex w-full items-center justify-center gap-2 rounded-lg bg-secondary py-2 text-sm font-semibold text-secondary-foreground transition-colors hover:bg-secondary/80 disabled:opacity-60"
              >
                {loadingPlan === pack.plan ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  "Buy Now"
                )}
              </button>
            </div>
          ))}
        </div>
      </div>

      {/* Trust footer */}
      <div className="flex items-center justify-center gap-6 text-xs text-muted-foreground">
        <div className="flex items-center gap-1.5">
          <CreditCard className="h-3.5 w-3.5" />
          Powered by Stripe
        </div>
        <div className="flex items-center gap-1.5">
          <Lock className="h-3.5 w-3.5" />
          256-bit SSL
        </div>
        <div className="flex items-center gap-1.5">
          <Shield className="h-3.5 w-3.5" />
          Cancel anytime
        </div>
      </div>
    </div>
  );
};

export default Pricing;
