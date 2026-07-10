import { describe, it, expect, vi, afterEach } from "vitest";
import { NextRequest } from "next/server";
import { GET } from "@/app/auth/callback/route";

vi.mock("@/lib/supabase/server", () => ({
  createClient: vi.fn(),
}));

import { createClient } from "@/lib/supabase/server";

function makeSupabaseClient(error: unknown = null) {
  return {
    auth: {
      exchangeCodeForSession: vi.fn().mockResolvedValue({ error }),
    },
  };
}

function makeRequest(query: string) {
  return new NextRequest(`http://localhost/auth/callback${query}`);
}

describe("GET /auth/callback", () => {
  afterEach(() => {
    vi.clearAllMocks();
  });

  it("redirects to /dashboard on a successful exchange with no redirect param", async () => {
    vi.mocked(createClient).mockResolvedValue(makeSupabaseClient() as never);

    const res = await GET(makeRequest("?code=abc123"));

    expect(res.status).toBe(307);
    expect(res.headers.get("location")).toBe("http://localhost/dashboard");
  });

  it("redirects to a valid redirect param on success", async () => {
    vi.mocked(createClient).mockResolvedValue(makeSupabaseClient() as never);

    const res = await GET(makeRequest("?code=abc123&redirect=%2Fchat"));

    expect(res.headers.get("location")).toBe("http://localhost/chat");
  });

  it("falls back to /dashboard when the redirect param is an open-redirect attempt", async () => {
    vi.mocked(createClient).mockResolvedValue(makeSupabaseClient() as never);

    const res = await GET(
      makeRequest("?code=abc123&redirect=" + encodeURIComponent("https://evil.com"))
    );

    expect(res.headers.get("location")).toBe("http://localhost/dashboard");
  });

  // Regression test: a real, successful sign-in (valid `code`, genuine
  // session established) must never end up redirecting the now-authenticated
  // user off-origin, even via a `redirect` param crafted to exploit WHATWG
  // URL's backslash-to-forward-slash normalization for special schemes
  // (`new URL("/\\evil.com", origin)` would otherwise resolve to
  // `https://evil.com/`).
  it("falls back to /dashboard when the redirect param is a backslash open-redirect payload", async () => {
    vi.mocked(createClient).mockResolvedValue(makeSupabaseClient() as never);

    const res = await GET(
      makeRequest("?code=abc123&redirect=" + encodeURIComponent("/\\evil.com"))
    );

    const location = res.headers.get("location")!;
    expect(location).toBe("http://localhost/dashboard");
    expect(new URL(location).origin).toBe("http://localhost");
  });

  it("redirects to /login?error=failed when there is no code", async () => {
    const res = await GET(makeRequest(""));

    expect(res.headers.get("location")).toBe("http://localhost/login?error=failed");
    expect(createClient).not.toHaveBeenCalled();
  });

  it("redirects to /login?error=failed when exchangeCodeForSession fails", async () => {
    vi.mocked(createClient).mockResolvedValue(
      makeSupabaseClient(new Error("bad code")) as never
    );

    const res = await GET(makeRequest("?code=bad-code"));

    expect(res.headers.get("location")).toBe("http://localhost/login?error=failed");
  });

  it("redirects to /login?error=cancelled when Google reports access_denied", async () => {
    const res = await GET(makeRequest("?error=access_denied"));

    expect(res.headers.get("location")).toBe("http://localhost/login?error=cancelled");
    expect(createClient).not.toHaveBeenCalled();
  });

  it("redirects to /login?error=failed for any other Google error", async () => {
    const res = await GET(makeRequest("?error=server_error"));

    expect(res.headers.get("location")).toBe("http://localhost/login?error=failed");
  });

  it("preserves a valid redirect param through to the login retry on failure", async () => {
    const res = await GET(makeRequest("?error=access_denied&redirect=%2Fdocuments"));

    const location = new URL(res.headers.get("location")!);
    expect(location.pathname).toBe("/login");
    expect(location.searchParams.get("error")).toBe("cancelled");
    expect(location.searchParams.get("redirect")).toBe("/documents");
  });

  it("drops an unsafe redirect param when preserving it through to the login retry", async () => {
    const res = await GET(
      makeRequest("?error=access_denied&redirect=" + encodeURIComponent("//evil.com"))
    );

    const location = new URL(res.headers.get("location")!);
    expect(location.searchParams.has("redirect")).toBe(false);
  });

  it("drops a backslash open-redirect payload when preserving redirect through to the login retry", async () => {
    const res = await GET(
      makeRequest("?error=access_denied&redirect=" + encodeURIComponent("/\\evil.com"))
    );

    const location = new URL(res.headers.get("location")!);
    expect(location.origin).toBe("http://localhost");
    expect(location.searchParams.has("redirect")).toBe(false);
  });
});
