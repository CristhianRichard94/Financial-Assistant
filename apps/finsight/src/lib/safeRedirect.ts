/**
 * Guards against open-redirect vulnerabilities in the `?redirect=` query
 * param used by `src/middleware.ts`, `src/app/login/page.tsx`, and
 * `src/app/auth/callback/route.ts`.
 *
 * Only accepts a value that is a same-origin, absolute path: it must start
 * with a single `/`, must not start with `//` (protocol-relative URL, which
 * browsers treat as pointing at a different origin), must not contain
 * `://` anywhere (which would allow e.g. `/x://evil.com` style payloads on
 * parsers lenient about a leading slash), and must not contain a backslash
 * (`\`) anywhere - the WHATWG URL spec (used by every major browser, by
 * Node's `URL`, and therefore by Next.js's own `new URL(...)` calls)
 * normalizes backslashes to forward slashes for "special" schemes like
 * http/https, so e.g. `/\evil.com` looks like a same-origin path by plain
 * string inspection but `new URL("/\\evil.com", origin)` actually resolves
 * to `https://evil.com/` - a different origin entirely. Anything that
 * fails these checks falls back to the given fallback path.
 *
 * On top of those fast, explicit checks, this also actually parses the
 * candidate as a URL (resolved against a fixed placeholder origin) and
 * verifies the origin didn't change - defense in depth against any other
 * URL-parsing quirk that changes the effective origin, not just the known
 * backslash case above.
 */

const PLACEHOLDER_ORIGIN = "http://safe-redirect.invalid";

export function safeRedirect(path: string | null | undefined, fallback = "/dashboard"): string {
  if (!path) return fallback;
  if (!path.startsWith("/")) return fallback;
  if (path.startsWith("//")) return fallback;
  if (path.includes("://")) return fallback;
  if (path.includes("\\")) return fallback;

  try {
    const resolved = new URL(path, PLACEHOLDER_ORIGIN);
    if (resolved.origin !== PLACEHOLDER_ORIGIN) return fallback;
  } catch {
    return fallback;
  }

  return path;
}
