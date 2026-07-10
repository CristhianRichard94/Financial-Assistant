import { createServerClient } from "@supabase/ssr";
import { cookies } from "next/headers";
import { getSupabaseAnonKey, getSupabaseUrl } from "@/lib/supabase/env";

/**
 * Supabase client for use in Server Components and Route Handlers.
 *
 * Security note: this client's `getUser()` must be used (not `getSession()`)
 * for any authorization decision, since `getUser()` revalidates the JWT
 * against the Supabase Auth server on every call, while `getSession()` only
 * decodes the session cookie locally without verifying it hasn't been
 * tampered with or revoked. See `src/lib/auth/requireUser.ts` and
 * `src/middleware.ts`.
 */
export async function createClient() {
  const cookieStore = await cookies();

  return createServerClient(getSupabaseUrl(), getSupabaseAnonKey(), {
    cookies: {
      getAll() {
        return cookieStore.getAll();
      },
      setAll(cookiesToSet) {
        try {
          cookiesToSet.forEach(({ name, value, options }) => {
            cookieStore.set(name, value, options);
          });
        } catch {
          // `setAll` was called from a Server Component, which cannot write
          // cookies. This is safe to ignore as long as `src/middleware.ts`
          // is refreshing the session cookie on every request.
        }
      },
    },
  });
}
