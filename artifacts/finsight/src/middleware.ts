import { NextResponse, type NextRequest } from "next/server";
import { updateSession } from "@/lib/supabase/middleware";
import { safeRedirect } from "@/lib/safeRedirect";

const PROTECTED_PREFIXES = ["/dashboard", "/chat", "/documents"];

function isProtectedPath(pathname: string): boolean {
  return PROTECTED_PREFIXES.some((prefix) => pathname === prefix || pathname.startsWith(`${prefix}/`));
}

export async function middleware(request: NextRequest) {
  // Always refresh the session cookie first, per the @supabase/ssr App
  // Router pattern - this keeps the user signed in across Server Component
  // renders even when nothing below needs to read `user`.
  const { supabaseResponse, user } = await updateSession(request);

  const { pathname, search } = request.nextUrl;

  if (isProtectedPath(pathname) && !user) {
    const loginUrl = new URL("/login", request.url);
    loginUrl.searchParams.set("redirect", safeRedirect(`${pathname}${search}`));
    return NextResponse.redirect(loginUrl);
  }

  return supabaseResponse;
}

export const config = {
  matcher: [
    /*
     * Run on every request except static assets and Next's internal
     * machinery, so the session cookie stays fresh app-wide (not just on
     * the protected routes) - but still exclude those to avoid wasted
     * Supabase calls on every image/font/etc. request.
     */
    "/((?!_next/static|_next/image|favicon.ico|.*\\.(?:svg|png|jpg|jpeg|gif|webp)$).*)",
  ],
};
