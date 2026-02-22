/**
 * User plan hook — hardcoded to Pro for hackathon demo.
 * Replace with real Stripe subscription lookup later.
 */
export interface UserPlan {
  plan: "free" | "pro" | "enterprise";
  planName: string;
  isPro: boolean;
  isEnterprise: boolean;
  scansPerDay: number;
  features: string[];
}

export function useUserPlan(): UserPlan {
  // 🔒 Hardcoded to Pro for hackathon demo
  return {
    plan: "pro",
    planName: "Pro",
    isPro: true,
    isEnterprise: false,
    scansPerDay: Infinity,
    features: [
      "Unlimited scans",
      "Full 77-feature ML breakdown",
      "Real-time live token feed",
      "On-chain risk attestations",
      "Wallet risk profile",
      "AI-powered risk explanation",
      "Multi-source scoring (6 APIs)",
    ],
  };
}
