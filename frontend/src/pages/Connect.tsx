import { useState } from "react";
import { Shield, Lock, Mail, Eye, EyeOff, ArrowRight, Zap, Activity, Wallet } from "lucide-react";
import { useAuth } from "@/hooks/useAuth";
import { useWallet } from "@solana/wallet-adapter-react";
import { WalletMultiButton } from "@solana/wallet-adapter-react-ui";
import Pricing from "@/pages/Pricing";

const Connect = () => {
  const { user, loading, signIn, signUp, signOut, walletAddress } = useAuth();
  const { disconnect, wallet, select } = useWallet();

  const handleDisconnect = async () => {
    try {
      // 1. Tell the adapter to disconnect from the wallet extension.
      if (wallet?.adapter) {
        await wallet.adapter.disconnect();
      } else {
        await disconnect();
      }
    } catch {
      // Swallow – some adapters throw after disconnect.
    }

    // 2. Nuke the cached wallet name so autoConnect can't silently reconnect.
    localStorage.removeItem("walletName");

    // 3. Tell the provider there is no selected wallet anymore.
    select(null as any);
  };
  const [isLogin, setIsLogin] = useState(true);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [checkEmail, setCheckEmail] = useState(false);

  if (loading) {
    return (
      <div className="flex min-h-[calc(100vh-4rem)] items-center justify-center">
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-primary border-t-transparent" />
      </div>
    );
  }

  if (user || walletAddress) {
    return (
      <div>
        <div className="container flex items-center justify-end py-3">
          <div className="flex items-center gap-3 text-sm">
            {walletAddress && (
              <div className="flex items-center gap-2">
                <Wallet className="h-3.5 w-3.5 text-primary" />
                <span className="font-mono text-xs text-muted-foreground">
                  {walletAddress.slice(0, 4)}...{walletAddress.slice(-4)}
                </span>
                <button
                  onClick={handleDisconnect}
                  className="rounded-lg bg-secondary px-3 py-1.5 text-xs font-medium text-secondary-foreground transition-colors hover:bg-secondary/80"
                >
                  Disconnect
                </button>
              </div>
            )}
            {user && (
              <>
                <span className="text-muted-foreground">{user.email}</span>
                <button
                  onClick={signOut}
                  className="rounded-lg bg-secondary px-3 py-1.5 text-xs font-medium text-secondary-foreground transition-colors hover:bg-secondary/80"
                >
                  Sign out
                </button>
              </>
            )}
          </div>
        </div>
        <Pricing />
      </div>
    );
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setSubmitting(true);

    const { error } = isLogin
      ? await signIn(email, password)
      : await signUp(email, password);

    if (error) {
      setError(error.message);
    } else if (!isLogin) {
      setCheckEmail(true);
    }
    setSubmitting(false);
  };

  if (checkEmail) {
    return (
      <div className="flex min-h-[calc(100vh-4rem)] items-center justify-center px-4">
        <div className="max-w-md text-center">
          <div className="mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-2xl bg-primary/20">
            <Mail className="h-8 w-8 text-primary" />
          </div>
          <h2 className="text-2xl font-bold text-foreground">Check your email</h2>
          <p className="mt-2 text-muted-foreground">
            We sent a confirmation link to <span className="font-medium text-foreground">{email}</span>.
            Click it to activate your account.
          </p>
          <button
            onClick={() => { setCheckEmail(false); setIsLogin(true); }}
            className="mt-6 text-sm font-medium text-primary hover:underline"
          >
            Back to login
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="flex min-h-[calc(100vh-4rem)]">
      {/* Left branding panel */}
      <div className="hidden flex-1 flex-col justify-center bg-gradient-to-br from-primary/10 via-card to-card p-12 lg:flex">
        <div className="space-y-10">
          <div>
            <div className="flex items-center gap-3">
              <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-primary/20">
                <Shield className="h-6 w-6 text-primary" />
              </div>
              <span className="text-xl font-bold text-foreground">DeFi Sentinel</span>
            </div>
            <p className="mt-1 text-sm text-muted-foreground">AI rug-pull detector</p>
          </div>

          <h2 className="text-3xl font-bold leading-tight text-foreground">
            Protect your portfolio<br />
            <span className="text-gradient">before you trade.</span>
          </h2>

          <div className="space-y-4">
            {[
              { icon: Shield, text: "AI-powered token analysis" },
              { icon: Zap, text: "Real-time rug-pull detection" },
              { icon: Activity, text: "77-feature risk breakdown" },
            ].map(({ icon: Icon, text }) => (
              <div key={text} className="flex items-center gap-3 text-sm text-muted-foreground">
                <Icon className="h-4 w-4 text-primary" />
                {text}
              </div>
            ))}
          </div>

          <p className="text-xs text-muted-foreground/60">
            Monitoring 116,000+ Solana pools in real-time
          </p>
        </div>
      </div>

      {/* Right form panel */}
      <div className="flex flex-1 items-center justify-center px-6">
        <div className="w-full max-w-sm">
          <h1 className="text-2xl font-bold text-foreground">
            {isLogin ? "Welcome back" : "Create account"}
          </h1>
          <p className="mt-1 text-sm text-muted-foreground">
            {isLogin ? "Sign in to access your dashboard" : "Start scanning tokens for free"}
          </p>

          {/* ── Solana Wallet Connect ───────────────── */}
          <div className="mt-6">
            <div className="flex items-center gap-2 mb-3">
              <Wallet className="h-4 w-4 text-primary" />
              <span className="text-sm font-semibold text-foreground">Connect with Solana Wallet</span>
            </div>
            <WalletMultiButton
              style={{
                width: "100%",
                height: "44px",
                borderRadius: "0.5rem",
                fontSize: "14px",
                fontWeight: 600,
                justifyContent: "center",
                background: "linear-gradient(135deg, #9945FF, #14F195)",
              }}
            />
            <p className="mt-2 text-center text-[10px] text-muted-foreground">
              Supports Phantom, Solflare &amp; more
            </p>
          </div>

          {/* ── Divider ───────────────── */}
          <div className="my-6 flex items-center gap-3">
            <div className="h-px flex-1 bg-border" />
            <span className="text-xs text-muted-foreground">or use email</span>
            <div className="h-px flex-1 bg-border" />
          </div>

          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="mb-1.5 block text-xs font-medium text-muted-foreground">Email</label>
              <div className="relative">
                <Mail className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
                <input
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  required
                  placeholder="you@example.com"
                  className="h-11 w-full rounded-lg border border-border bg-card pl-10 pr-4 text-sm text-foreground placeholder:text-muted-foreground focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
                />
              </div>
            </div>

            <div>
              <label className="mb-1.5 block text-xs font-medium text-muted-foreground">Password</label>
              <div className="relative">
                <Lock className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
                <input
                  type={showPassword ? "text" : "password"}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  required
                  minLength={6}
                  placeholder="••••••••"
                  className="h-11 w-full rounded-lg border border-border bg-card pl-10 pr-10 text-sm text-foreground placeholder:text-muted-foreground focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
                >
                  {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                </button>
              </div>
            </div>

            {error && (
              <p className="rounded-lg bg-danger/10 px-3 py-2 text-xs text-danger">{error}</p>
            )}

            <button
              type="submit"
              disabled={submitting}
              className="flex h-11 w-full items-center justify-center gap-2 rounded-lg bg-primary text-sm font-semibold text-primary-foreground transition-all hover:opacity-90 disabled:opacity-50"
            >
              {submitting ? (
                <div className="h-4 w-4 animate-spin rounded-full border-2 border-primary-foreground border-t-transparent" />
              ) : (
                <>
                  {isLogin ? "Sign in" : "Create account"}
                  <ArrowRight className="h-4 w-4" />
                </>
              )}
            </button>
          </form>

          <p className="mt-6 text-center text-xs text-muted-foreground">
            {isLogin ? "Don't have an account?" : "Already have an account?"}{" "}
            <button
              onClick={() => { setIsLogin(!isLogin); setError(""); }}
              className="font-medium text-primary hover:underline"
            >
              {isLogin ? "Sign up" : "Sign in"}
            </button>
          </p>
        </div>
      </div>
    </div>
  );
};

export default Connect;
