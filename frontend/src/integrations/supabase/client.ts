import { createClient, SupabaseClient } from '@supabase/supabase-js';
import type { Database } from './types';

const SUPABASE_URL = import.meta.env.VITE_SUPABASE_URL ?? '';
const SUPABASE_PUBLISHABLE_KEY = import.meta.env.VITE_SUPABASE_PUBLISHABLE_KEY ?? '';

// Will be a real client when env vars are set, otherwise a dummy that won't crash the app
export const supabase: SupabaseClient<Database> = SUPABASE_URL && SUPABASE_PUBLISHABLE_KEY
  ? createClient<Database>(SUPABASE_URL, SUPABASE_PUBLISHABLE_KEY, {
      auth: {
        storage: localStorage,
        persistSession: true,
        autoRefreshToken: true,
      },
    })
  : (new Proxy({} as SupabaseClient<Database>, {
      get: (_target, prop) => {
        if (prop === 'auth') {
          return {
            onAuthStateChange: () => ({ data: { subscription: { unsubscribe: () => {} } } }),
            getSession: () => Promise.resolve({ data: { session: null }, error: null }),
            signUp: () => Promise.resolve({ error: { message: 'Supabase not configured' } }),
            signInWithPassword: () => Promise.resolve({ error: { message: 'Supabase not configured' } }),
            signOut: () => Promise.resolve(),
          };
        }
        if (prop === 'functions') {
          return { invoke: () => Promise.resolve({ data: null, error: { message: 'Supabase not configured' } }) };
        }
        return () => {};
      },
    }));
