import { useMemo, useCallback, ReactNode } from "react";
import {
  ConnectionProvider,
  WalletProvider,
} from "@solana/wallet-adapter-react";
import { WalletModalProvider } from "@solana/wallet-adapter-react-ui";
import { PhantomWalletAdapter, SolflareWalletAdapter } from "@solana/wallet-adapter-wallets";
import { clusterApiUrl } from "@solana/web3.js";

import "@solana/wallet-adapter-react-ui/styles.css";

/** localStorage key set by handleDisconnect to suppress silent reconnect */
export const MANUAL_DISCONNECT_KEY = "wallet-manual-disconnect";

/**
 * Wraps the app with Solana wallet connectivity.
 * Uses devnet for hackathon demo — switch to mainnet-beta for production.
 *
 * `autoConnect` is a callback: it returns `false` when the user has
 * explicitly disconnected, forcing them to pick a wallet again via the
 * WalletMultiButton modal. The flag is cleared the moment they reconnect.
 */
export default function SolanaWalletProvider({ children }: { children: ReactNode }) {
  const endpoint = useMemo(() => clusterApiUrl("devnet"), []);
  const wallets = useMemo(
    () => [new PhantomWalletAdapter(), new SolflareWalletAdapter()],
    [],
  );

  /**
   * Returning false prevents the silent reconnect.
   * Returning true lets the default autoConnect proceed.
   */
  const autoConnect = useCallback(() => {
    if (localStorage.getItem(MANUAL_DISCONNECT_KEY)) {
      return false;
    }
    return true;
  }, []);

  return (
    <ConnectionProvider endpoint={endpoint}>
      <WalletProvider wallets={wallets} autoConnect={autoConnect}>
        <WalletModalProvider>{children}</WalletModalProvider>
      </WalletProvider>
    </ConnectionProvider>
  );
}
