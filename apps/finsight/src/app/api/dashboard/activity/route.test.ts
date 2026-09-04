import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { NextResponse } from "next/server";
import { GET } from "@/app/api/dashboard/activity/route";
import type { Transaction } from "@/lib/types";

vi.mock("@/lib/auth/requireUser", () => ({
  requireUser: vi.fn(),
}));

vi.mock("@/lib/ragApiClient", async () => {
  const actual = await vi.importActual<typeof import("@/lib/ragApiClient")>("@/lib/ragApiClient");
  return {
    ...actual,
    getDashboardActivity: vi.fn(),
  };
});

import { requireUser } from "@/lib/auth/requireUser";
import { getDashboardActivity, RagApiError } from "@/lib/ragApiClient";

const TEST_USER = { id: "user-1", email: "user@example.com" };

const ACTIVITY: Transaction[] = [
  {
    id: "tx-1",
    description: "Whole Foods Market",
    category: "Groceries",
    amount: -87.43,
    date: "2026-01-01T00:00:00.000Z",
  },
];

describe("GET /api/dashboard/activity", () => {
  beforeEach(() => {
    vi.mocked(requireUser).mockResolvedValue({ user: TEST_USER as never });
    vi.mocked(getDashboardActivity).mockResolvedValue(ACTIVITY);
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it("returns 401 when there is no session", async () => {
    vi.mocked(requireUser).mockResolvedValue({
      response: NextResponse.json({ error: "Unauthorized" }, { status: 401 }),
    });

    const res = await GET(new Request("http://localhost/api/dashboard/activity", { headers: { "x-request-id": "test-request-id" } }));
    const body = await res.json();

    expect(res.status).toBe(401);
    expect(body).toEqual({ error: "Unauthorized" });
  });

  it("returns recent activity from rag-api as JSON", async () => {
    const res = await GET(new Request("http://localhost/api/dashboard/activity", { headers: { "x-request-id": "test-request-id" } }));
    const body = await res.json();

    expect(res.status).toBe(200);
    expect(body).toEqual(ACTIVITY);
    expect(getDashboardActivity).toHaveBeenCalledWith(TEST_USER.id, "test-request-id");
  });

  it("returns a list of transactions with the expected shape", async () => {
    const res = await GET(new Request("http://localhost/api/dashboard/activity", { headers: { "x-request-id": "test-request-id" } }));
    const body = await res.json();

    expect(Array.isArray(body)).toBe(true);
    expect(body[0]).toMatchObject({
      id: expect.any(String),
      description: expect.any(String),
      category: expect.any(String),
      amount: expect.any(Number),
      date: expect.any(String),
    });
  });

  it("passes through the rag-api error status on failure", async () => {
    vi.mocked(getDashboardActivity).mockRejectedValue(new RagApiError(502, "boom"));

    const res = await GET(new Request("http://localhost/api/dashboard/activity", { headers: { "x-request-id": "test-request-id" } }));
    const body = await res.json();

    expect(res.status).toBe(502);
    expect(body).toEqual({ error: "Failed to load recent activity" });
  });
});
