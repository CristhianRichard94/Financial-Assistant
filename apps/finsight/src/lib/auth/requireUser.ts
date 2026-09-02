import { NextResponse } from "next/server";
import type { User } from "@supabase/supabase-js";
import { createClient } from "@/lib/supabase/server";

export type RequireUserResult =
  | { user: User; response?: undefined }
  | { user?: undefined; response: NextResponse };

/**
 * Route Handler guard: verifies the caller has a real, revalidated Supabase
 * Auth session and returns the signed-in user, or a ready-to-return 401 JSON
 * response if there isn't one.
 *
 * Uses `supabase.auth.getUser()` (not `getSession()`), which revalidates the
 * JWT against the Supabase Auth server rather than just decoding the local
 * cookie - see `src/lib/supabase/server.ts`.
 *
 * This check is required in every Route Handler even though
 * `src/middleware.ts` already redirects unauthenticated *page* requests:
 * middleware only covers page navigations, and a client-side redirect (or a
 * request that bypasses the browser entirely, e.g. a direct API call) must
 * never be trusted as the sole access control.
 *
 * Usage:
 *   const { user, response } = await requireUser();
 *   if (!user) return response;
 */
export async function requireUser(): Promise<RequireUserResult> {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();

  if (!user) {
    return { response: NextResponse.json({ error: "Unauthorized" }, { status: 401 }) };
  }

  return { user };
}
