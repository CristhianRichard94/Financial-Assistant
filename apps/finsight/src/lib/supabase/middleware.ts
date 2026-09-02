import { createServerClient } from "@supabase/ssr";
import { NextResponse, type NextRequest } from "next/server";
import type { User } from "@supabase/supabase-js";
import { getSupabaseAnonKey, getSupabaseUrl } from "@/lib/supabase/env";

/**
 * Refreshes the Supabase session cookie for a request in `src/middleware.ts`
 * and returns the (revalidated) signed-in user, if any.
 *
 * Uses `supabase.auth.getUser()` rather than `getSession()` to decide
 * whether the request is authenticated: `getUser()` revalidates the JWT
 * against the Supabase Auth server, while `getSession()` only decodes the
 * local cookie without verifying it - relying on `getSession()` alone here
 * would let a tampered or already-revoked cookie pass as authenticated.
 */
export async function updateSession(
  request: NextRequest
): Promise<{ supabaseResponse: NextResponse; user: User | null }> {
  let supabaseResponse = NextResponse.next({ request });

  const supabase = createServerClient(getSupabaseUrl(), getSupabaseAnonKey(), {
    cookies: {
      getAll() {
        return request.cookies.getAll();
      },
      setAll(cookiesToSet) {
        cookiesToSet.forEach(({ name, value }) => request.cookies.set(name, value));
        supabaseResponse = NextResponse.next({ request });
        cookiesToSet.forEach(({ name, value, options }) => {
          supabaseResponse.cookies.set(name, value, options);
        });
      },
    },
  });

  const {
    data: { user },
  } = await supabase.auth.getUser();

  return { supabaseResponse, user };
}
