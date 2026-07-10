import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { NextResponse } from "next/server";
import { GET } from "@/app/api/dashboard/activity/route";
import { store } from "@/lib/store";

vi.mock("@/lib/auth/requireUser", () => ({
  requireUser: vi.fn(),
}));

import { requireUser } from "@/lib/auth/requireUser";

const TEST_USER = { id: "user-1", email: "user@example.com" };

describe("GET /api/dashboard/activity", () => {
  beforeEach(() => {
    vi.mocked(requireUser).mockResolvedValue({ user: TEST_USER as never });
    // `store.dashboard.activity()` computes each transaction's `id` (nanoid)
    // and `date` (relative to `Date.now()`) fresh on every call. Freeze the
    // clock so a second, independent call made in the test for comparison
    // produces the same `date` values as the one made by `GET()`.
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-01-01T00:00:00.000Z"));
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.clearAllMocks();
  });

  it("returns 401 when there is no session", async () => {
    vi.mocked(requireUser).mockResolvedValue({
      response: NextResponse.json({ error: "Unauthorized" }, { status: 401 }),
    });

    const res = await GET();
    const body = await res.json();

    expect(res.status).toBe(401);
    expect(body).toEqual({ error: "Unauthorized" });
  });

  it("returns the store's recent activity as JSON", async () => {
    const res = await GET();
    const body = await res.json();

    // `store.dashboard.activity()` also generates a fresh `id` (nanoid) per
    // call, so compare everything except `id` rather than deep-equaling
    // against a second independent call.
    const expected = store.dashboard.activity();
    expect(res.status).toBe(200);
    expect(body).toHaveLength(expected.length);
    expect(body.map((tx: { id: string; [k: string]: unknown }) => {
      const { id, ...rest } = tx;
      return rest;
    })).toEqual(
      expected.map(({ id, ...rest }) => rest)
    );
  });

  it("returns a list of transactions with the expected shape", async () => {
    const res = await GET();
    const body = await res.json();

    expect(Array.isArray(body)).toBe(true);
    expect(body.length).toBeGreaterThan(0);
    expect(body[0]).toMatchObject({
      id: expect.any(String),
      description: expect.any(String),
      category: expect.any(String),
      amount: expect.any(Number),
      date: expect.any(String),
    });
  });
});
