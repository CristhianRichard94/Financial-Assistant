import { NextRequest, NextResponse } from "next/server";
import { createClient } from "@/lib/supabase/server";
import { safeRedirect } from "@/lib/safeRedirect";

/**
 * OAuth callback landing page for Google sign-in via Supabase Auth.
 *
 * Google redirects the browser here (via Supabase's own `/auth/v1/callback`
 * first - see artifacts/finsight/README.md for the required Supabase/Google
 * Cloud Console configuration) with either a `code` to exchange for a
 * session, or an `error` describing why sign-in didn't happen.
 */
export async function GET(request: NextRequest) {
  const { searchParams, origin } = request.nextUrl;
  const code = searchParams.get("code");
  const errorParam = searchParams.get("error");
  const redirectParam = searchParams.get("redirect");

  function loginRedirectUrl(errorType: "cancelled" | "failed"): URL {
    const url = new URL("/login", origin);
    url.searchParams.set("error", errorType);
    // Preserve a valid `redirect` param through to the retry, so the user
    // lands back where they originally intended after signing in again.
    const preservedTarget = safeRedirect(redirectParam, "");
    if (preservedTarget) {
      url.searchParams.set("redirect", preservedTarget);
    }
    return url;
  }

  // Google reports `error=access_denied` when the user cancels the consent
  // screen; anything else is a genuine failure.
  if (errorParam) {
    const errorType = errorParam === "access_denied" ? "cancelled" : "failed";
    return NextResponse.redirect(loginRedirectUrl(errorType));
  }

  if (!code) {
    return NextResponse.redirect(loginRedirectUrl("failed"));
  }

  const supabase = await createClient();
  const { error } = await supabase.auth.exchangeCodeForSession(code);

  if (error) {
    return NextResponse.redirect(loginRedirectUrl("failed"));
  }

  const destination = safeRedirect(redirectParam);
  return NextResponse.redirect(new URL(destination, origin));
}
