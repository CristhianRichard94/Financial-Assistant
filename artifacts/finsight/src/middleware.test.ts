import { describe, it, expect, vi, afterEach } from "vitest";
import { NextRequest, NextResponse } from "next/server";
import { middleware } from "@/middleware";

vi.mock("@/lib/supabase/middleware", () => ({
  updateSession: vi.fn(),
}));

import { updateSession } from "@/lib/supabase/middleware";

function makeRequest(pathAndQuery: string) {
  return new NextRequest(`http://localhost${pathAndQuery}`);
}

function mockSession(user: unknown) {
  const supabaseResponse = NextResponse.next();
  vi.mocked(updateSession).mockResolvedValue({ supabaseResponse, user } as never);
  return supabaseResponse;
}

describe("middleware", () => {
  afterEach(() => {
    vi.clearAllMocks();
  });

  it("redirects a signed-out request to a protected path to /login with a redirect param", async () => {
    mockSession(null);

    const res = await middleware(makeRequest("/dashboard"));

    expect(res.status).toBe(307);
    expect(res.headers.get("location")).toBe("http://localhost/login?redirect=%2Fdashboard");
  });

  it("preserves the query string in the redirect param", async () => {
    mockSession(null);

    const res = await middleware(makeRequest("/documents?tab=uploaded"));

    const location = new URL(res.headers.get("location")!);
    expect(location.pathname).toBe("/login");
    expect(location.searchParams.get("redirect")).toBe("/documents?tab=uploaded");
  });

  it("redirects a signed-out request to a nested protected path", async () => {
    mockSession(null);

    const res = await middleware(makeRequest("/documents/123"));

    const location = new URL(res.headers.get("location")!);
    expect(location.searchParams.get("redirect")).toBe("/documents/123");
  });

  it.each(["/dashboard", "/chat", "/documents"])(
    "redirects a signed-out request to %s",
    async (path) => {
      mockSession(null);

      const res = await middleware(makeRequest(path));

      expect(res.status).toBe(307);
      expect(new URL(res.headers.get("location")!).pathname).toBe("/login");
    }
  );

  it("passes through a signed-out request to a non-protected path (e.g. /login itself)", async () => {
    const supabaseResponse = mockSession(null);

    const res = await middleware(makeRequest("/login"));

    expect(res).toBe(supabaseResponse);
  });

  it("passes through a signed-in request to a protected path", async () => {
    const supabaseResponse = mockSession({ id: "user-1" });

    const res = await middleware(makeRequest("/dashboard"));

    expect(res).toBe(supabaseResponse);
  });

  it("does not treat an unrelated path prefixed similarly as protected", async () => {
    const supabaseResponse = mockSession(null);

    // "/documentsomething" starts with "/documents" as a raw string but is
    // not actually nested under it - must not be redirected.
    const res = await middleware(makeRequest("/documentsomething"));

    expect(res).toBe(supabaseResponse);
  });
});
