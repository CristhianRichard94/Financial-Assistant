import { describe, it, expect } from "vitest";
import { safeRedirect } from "@/lib/safeRedirect";

describe("safeRedirect", () => {
  it("returns the default fallback when the path is null", () => {
    expect(safeRedirect(null)).toBe("/dashboard");
  });

  it("returns the default fallback when the path is undefined", () => {
    expect(safeRedirect(undefined)).toBe("/dashboard");
  });

  it("returns the default fallback when the path is an empty string", () => {
    expect(safeRedirect("")).toBe("/dashboard");
  });

  it("accepts a simple absolute path", () => {
    expect(safeRedirect("/chat")).toBe("/chat");
  });

  it("accepts an absolute path with a query string", () => {
    expect(safeRedirect("/documents?foo=bar")).toBe("/documents?foo=bar");
  });

  it("rejects a path not starting with a slash", () => {
    expect(safeRedirect("chat")).toBe("/dashboard");
  });

  it("rejects a protocol-relative URL (//)", () => {
    expect(safeRedirect("//evil.com")).toBe("/dashboard");
  });

  it("rejects an absolute URL to another origin", () => {
    expect(safeRedirect("https://evil.com")).toBe("/dashboard");
  });

  it("rejects a path containing :// anywhere", () => {
    expect(safeRedirect("/redirect?to=http://evil.com")).toBe("/dashboard");
  });

  // Regression coverage for a WHATWG URL-parsing bypass: browsers, Node's
  // `URL`, and therefore Next.js's own `new URL(...)` calls treat a
  // backslash as equivalent to a forward slash for special schemes like
  // http/https. `new URL("/\\evil.com", "https://good.com").href` resolves
  // to `"https://evil.com/"` even though the string itself starts with a
  // single `/` and contains neither `//` nor `://`.
  it("rejects a path containing a literal backslash (WHATWG backslash-normalization bypass)", () => {
    expect(safeRedirect("/\\evil.com")).toBe("/dashboard");
  });

  it("rejects a path containing a backslash followed by a forward slash", () => {
    expect(safeRedirect("/\\/evil.com")).toBe("/dashboard");
  });

  it("rejects a path with a backslash appearing after the leading segment", () => {
    expect(safeRedirect("/dashboard/\\evil.com")).toBe("/dashboard");
  });

  it("confirms the exact exploit payload would otherwise change origin", () => {
    // Sanity-check the premise of the regression tests above: without the
    // backslash guard, this payload really would resolve to a different
    // origin when later passed to `new URL(destination, origin)` (as
    // src/app/auth/callback/route.ts and src/app/login/page.tsx do).
    const resolved = new URL("/\\evil.com", "https://good.example");
    expect(resolved.origin).toBe("https://evil.com");
  });

  it("uses a custom fallback when provided", () => {
    expect(safeRedirect(null, "/login")).toBe("/login");
    expect(safeRedirect("javascript://evil", "/login")).toBe("/login");
    expect(safeRedirect("/\\evil.com", "/login")).toBe("/login");
  });
});
