/* Buffer polyfill — Solana web3.js requires Node.js Buffer in the browser */
import { Buffer } from "buffer";
(window as any).Buffer = Buffer;
