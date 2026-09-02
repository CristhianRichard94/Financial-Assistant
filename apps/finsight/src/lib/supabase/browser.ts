import { createBrowserClient } from "@supabase/ssr";
import { getSupabaseAnonKey, getSupabaseUrl } from "@/lib/supabase/env";

/**
 * Supabase client for use in Client Components (e.g. the login page's sign-in
 * button, `AppLayout`'s logout action). Reads/writes the session via
 * browser cookies - never a service-role key.
 */
export function createClient() {
  return createBrowserClient(getSupabaseUrl(), getSupabaseAnonKey());
}
