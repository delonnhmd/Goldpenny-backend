/**
 * Supabase Auth client for Gold Penny (Step 95E).
 *
 * Setup required before this module will work:
 *   1) yarn add @supabase/supabase-js
 *   2) Set EXPO_PUBLIC_SUPABASE_URL and EXPO_PUBLIC_SUPABASE_ANON_KEY in
 *      the Expo env (e.g. .env.local + app.config.js extras).
 *
 * Supabase auth user.id is the canonical identity passed to the backend
 * via GET /player/by-user-id/{user_id}. The backend owns player creation.
 */
import 'react-native-url-polyfill/auto';
import 'react-native-get-random-values';

import AsyncStorage from '@react-native-async-storage/async-storage';
import { createClient, SupabaseClient } from '@supabase/supabase-js';

// Expo only inlines env vars prefixed with EXPO_PUBLIC_. Accept the common
// NEXT_PUBLIC_ prefix as a fallback so a copy/paste from a Next.js project
// still works during development.
const SUPABASE_URL =
  process.env.EXPO_PUBLIC_SUPABASE_URL ||
  process.env.NEXT_PUBLIC_SUPABASE_URL ||
  '';
const SUPABASE_ANON_KEY =
  process.env.EXPO_PUBLIC_SUPABASE_ANON_KEY ||
  process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY ||
  '';

if (!SUPABASE_URL || !SUPABASE_ANON_KEY) {
  throw new Error(
    '[supabase] Missing EXPO_PUBLIC_SUPABASE_URL or EXPO_PUBLIC_SUPABASE_ANON_KEY. ' +
      'Add them to expo/.env.local (use the EXPO_PUBLIC_ prefix — NEXT_PUBLIC_ is for Next.js, ' +
      'Expo will not expose it) and restart Metro with `yarn start --clear`.',
  );
}

export const supabase: SupabaseClient = createClient(SUPABASE_URL, SUPABASE_ANON_KEY, {
  auth: {
    storage: AsyncStorage as any,
    autoRefreshToken: true,
    persistSession: true,
    detectSessionInUrl: false,
  },
});

export async function getCurrentSupabaseUserId(): Promise<string | null> {
  const { data, error } = await supabase.auth.getUser();
  if (error || !data?.user?.id) return null;
  return data.user.id;
}

export async function signOutSupabase(): Promise<void> {
  await supabase.auth.signOut();
}
