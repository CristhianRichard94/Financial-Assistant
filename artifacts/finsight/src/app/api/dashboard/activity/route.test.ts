import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { GET } from "@/app/api/dashboard/activity/route";
import { store } from "@/lib/store";

describe("GET /api/dashboard/activity", () => {
  beforeEach(() => {
    // `store.dashboard.activity()` computes each transaction's `id` (nanoid)
    // and `date` (relative to `Date.now()`) fresh on every call. Freeze the
    // clock so a second, independent call made in the test for comparison
    // produces the same `date` values as the one made by `GET()`.
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-01-01T00:00:00.000Z"));
  });

  afterEach(() => {
    vi.useRealTimers();
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
