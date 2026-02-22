import { useState, useEffect } from "react";
import { Check, Shield, CreditCard, Lock, X, Loader2, Wallet, Crown, CheckCircle2 } from "lucide-react";
import { useWallet } from "@solana/wallet-adapter-react";
import { useConnection } from "@solana/wallet-adapter-react";
import { SystemProgram, Transaction, PublicKey, LAMPORTS_PER_SOL } from "@solana/web3.js";
import { getPayerAddress, verifyPayment, getCredits, PayerInfo } from "@/lib/solana";
import { useUserPlan } from "@/hooks/useUserPlan";

const tiers = [
  {
    name: "Free",
    price: 0,
    period: "forever",
    description: "Start scanning tokens today",
    badge: null,
    variant: "default" as const,
    plan: "free",
    features: ["3 scans/day", "Basic risk score", "Live token feed", "Community support"],
    excluded: ["Full 77-feature breakdown", "On-chain attestations", "Wallet risk profile", "AI explanation"],
    cta: "Downgrade",
  },
  {
    name: "Pro",
    price: 9.99,
    period: "/month",
    description: "For active traders & researchers",
    badge: "MOST POPULAR",
    variant: "popular" as const,
    plan: "pro",
    features: [
      "Unlimited scans",
      "Full 77-feature ML breakdown",
      "Real-time live token feed",
      "On-chain risk attestations",
      "Wallet risk profile",
      "AI-powered risk explanation",
      "Multi-source scoring (6 APIs)",
    ],
    excluded: [],
    cta: "Subscribe with Stripe",
  },
  {
    name: "Enterprise",
    price: 99.99,
    period: "/month",
    description: "For wallets, DEXs & platforms",
    badge: "FOR WALLETS & DEXS",
    variant: "enterprise" as const,
    plan: "enterprise",
    features: [
      "Everything in Pro",
      "Unlimited API access",
      "WebSocket real-time feed",
      "Wallet portfolio scanning",
      "Stripe + SOL payments",
      "Co-signed wallet attestations",
      "Priority support & SLA",
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
  const [solLoading, setSolLoading] = useState<string | null>(null);
  const [solSuccess, setSolSuccess] = useState<string | null>(null);
  const [solError, setSolError] = useState("");
  const [payerInfo, setPayerInfo] = useState<PayerInfo | null>(null);
  const [credits, setCredits] = useState(0);
  const { publicKey, sendTransaction } = useWallet();
  const { connection } = useConnection();
  const { plan: currentPlan } = useUserPlan();

  // Load payer address + prices
  useEffect(() => {
    getPayerAddress().then(setPayerInfo).catch(() => {});
  }, []);

  // Load credits when wallet changes
  useEffect(() => {
    if (publicKey) {
      getCredits(publicKey.toBase58()).then((r) => setCredits(r.credits)).catch(() => {});
    }
  }, [publicKey?.toBase58()]);

  const handleSolPayment = async (plan: string) => {
    if (!publicKey || !payerInfo) return;
    setSolLoading(plan);
    setSolError("");
    setSolSuccess(null);
    try {
      const solAmount = payerInfo.solPrices[plan];
      if (!solAmount) throw new Error("Unknown plan");

      // Create SOL transfer transaction
      const tx = new Transaction().add(
        SystemProgram.transfer({
          fromPubkey: publicKey,
          toPubkey: new PublicKey(payerInfo.address),
          lamports: Math.round(solAmount * LAMPORTS_PER_SOL),
        }),
      );

      // User signs and sends via wallet
      const signature = await sendTransaction(tx, connection);

      // Wait for confirmation
      await connection.confirmTransaction(signature, "confirmed");

      // Verify with backend and credit scans
      const result = await verifyPayment(signature, plan, publicKey.toBase58());
      setCredits(result.totalCredits);
      setSolSuccess(`Payment confirmed! +${result.creditsAdded} scans credited.`);
    } catch (err: any) {
      setSolError(err.message || "SOL payment failed");
    } finally {
      setSolLoading(null);
    }
  };

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
        <div className="mb-3 inline-flex items-center gap-2 rounded-full border border-primary/40 bg-primary/10 px-4 py-1.5">
          <Crown className="h-4 w-4 text-primary" />
          <span className="text-sm font-bold text-primary">Pro Plan Active</span>
          <CheckCircle2 className="h-4 w-4 text-safe" />
        </div>
        <h1 className="text-3xl font-bold text-foreground">Protect Your Portfolio</h1>
        <p className="mt-2 text-muted-foreground">You're on the <span className="font-semibold text-primary">Pro plan</span> — all premium features unlocked</p>
      </div>

      {/* Tiers */}
      <div className="mb-16 grid gap-6 md:grid-cols-3">
        {tiers.map((tier) => {
          const isCurrentPlan = tier.plan === currentPlan;
          return (
          <div
            key={tier.name}
            className={`rounded-xl border p-6 transition-all duration-300 hover:-translate-y-1 ${isCurrentPlan ? "border-safe/50 bg-card ring-2 ring-safe/20 relative" : tierStyles[tier.variant]}`}
          >
            {isCurrentPlan && (
              <div className="absolute -top-3 left-1/2 -translate-x-1/2 flex items-center gap-1.5 rounded-full bg-safe px-3 py-1">
                <CheckCircle2 className="h-3 w-3 text-white" />
                <span className="text-[10px] font-bold uppercase tracking-wider text-white">Current Plan</span>
              </div>
            )}
            {tier.badge && !isCurrentPlan && (
              <span className="mb-4 inline-block rounded-full bg-primary/15 px-3 py-1 text-[10px] font-bold uppercase tracking-wider text-primary">
                {tier.badge}
              </span>
            )}
            {tier.badge && isCurrentPlan && (
              <span className="mb-4 inline-block rounded-full bg-safe/15 px-3 py-1 text-[10px] font-bold uppercase tracking-wider text-safe">
                SUBSCRIBED
              </span>
            )}
            <h3 className="text-lg font-bold text-foreground">{tier.name}</h3>
            <p className="mt-1 text-xs text-muted-foreground">{tier.description}</p>
            <div className="mt-4 flex items-baseline gap-1">
              <span className="text-4xl font-black text-foreground">${tier.price}</span>
              <span className="text-sm text-muted-foreground">{tier.period}</span>
            </div>

            <button
              onClick={() => tier.plan && tier.plan !== "free" && !isCurrentPlan && handleCheckout(tier.plan)}
              disabled={tier.plan === "free" || loadingPlan === tier.plan || isCurrentPlan}
              className={`mt-6 flex w-full items-center justify-center gap-2 rounded-lg py-2.5 text-sm font-semibold transition-all disabled:opacity-60 ${
                isCurrentPlan
                  ? "bg-safe/15 text-safe border border-safe/30 cursor-default"
                  : tier.plan === "free"
                    ? "bg-secondary/50 text-muted-foreground cursor-not-allowed"
                    : ctaStyles[tier.variant]
              }`}
            >
              {isCurrentPlan ? (
                <><CheckCircle2 className="h-4 w-4" /> Current Plan</>
              ) : loadingPlan === tier.plan ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                tier.cta
              )}
            </button>

            {tier.plan && tier.plan !== "free" && !isCurrentPlan && (
              <p className="mt-2 text-center text-[10px] text-muted-foreground">7-day free trial included</p>
            )}
            {isCurrentPlan && (
              <p className="mt-2 text-center text-[10px] text-safe">✓ All Pro features unlocked</p>
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
          );
        })}
      </div>

      {/* Pay-per-scan */}
      <div className="mb-16">
        <h2 className="mb-6 text-center text-xl font-bold text-foreground">Pay-Per-Scan Packs</h2>

        {/* Credits banner */}
        {publicKey && (
          <div className="mb-4 flex items-center justify-center gap-3 rounded-lg border border-primary/30 bg-primary/5 px-4 py-3">
            <Wallet className="h-4 w-4 text-primary" />
            <span className="text-sm font-semibold text-foreground">
              {credits} scan credits
            </span>
            <span className="text-xs text-muted-foreground">
              · {publicKey.toBase58().slice(0, 4)}...{publicKey.toBase58().slice(-4)}
            </span>
          </div>
        )}

        {/* SOL payment status */}
        {solSuccess && (
          <div className="mb-4 rounded-lg bg-safe/10 border border-safe/30 px-4 py-3 text-sm text-safe text-center">
            ✅ {solSuccess}
          </div>
        )}
        {solError && (
          <div className="mb-4 rounded-lg bg-danger/10 border border-danger/30 px-4 py-3 text-sm text-danger text-center">
            {solError}
          </div>
        )}

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
                  <>
                    <CreditCard className="h-3.5 w-3.5" />
                    Pay with Stripe
                  </>
                )}
              </button>

              {/* SOL payment option */}
              {publicKey && payerInfo ? (
                <button
                  onClick={() => handleSolPayment(pack.plan)}
                  disabled={solLoading === pack.plan}
                  className="mt-2 flex w-full items-center justify-center gap-2 rounded-lg py-2 text-sm font-semibold text-white transition-all hover:opacity-90 disabled:opacity-50"
                  style={{ background: "linear-gradient(135deg, #9945FF, #14F195)" }}
                >
                  {solLoading === pack.plan ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : (
                    <>
                      <Wallet className="h-3.5 w-3.5" />
                      Pay {payerInfo.solPrices[pack.plan]} SOL
                    </>
                  )}
                </button>
              ) : (
                <p className="mt-2 text-center text-[10px] text-muted-foreground">
                  Connect wallet for SOL payment
                </p>
              )}
            </div>
          ))}
        </div>
      </div>

      {/* Trust footer */}
      <div className="flex flex-wrap items-center justify-center gap-6 text-xs text-muted-foreground">
        <div className="flex items-center gap-1.5">
          <CreditCard className="h-3.5 w-3.5" />
          Powered by Stripe
        </div>
        <div className="flex items-center gap-1.5">
          <Wallet className="h-3.5 w-3.5" />
          SOL Payments
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
