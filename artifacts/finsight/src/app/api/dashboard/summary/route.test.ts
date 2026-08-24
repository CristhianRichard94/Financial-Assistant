import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { NextResponse } from "next/server";
import { GET } from "@/app/api/dashboard/summary/route";
import type { DashboardSummary } from "@/lib/types";

vi.mock("@/lib/auth/requireUser", () => ({
  requireUser: vi.fn(),
}));

vi.mock("@/lib/ragApiClient", async () => {
  const actual = await vi.importActual<typeof import("@/lib/ragApiClient")>("@/lib/ragApiClient");
  return {
    ...actual,
    getDashboardSummary: vi.fn(),
  };
});

import { requireUser } from "@/lib/auth/requireUser";
import { getDashboardSummary, RagApiError } from "@/lib/ragApiClient";

const TEST_USER = { id: "user-1", email: "user@example.com" };

const SUMMARY: DashboardSummary = {
  totalIncome: 2000,
  totalSpending: -500,
  netSavings: 1500,
  incomeTrend: 10,
  spendingTrend: -5,
  savingsTrend: 20,
  documentCount: 2,
  totalDocumentCount: 3,
  transactionCount: 10,
  categoryBreakdown: [{ category: "Housing", amount: 300, percentage: 60 }],
};

describe("GET /api/dashboard/summary", () => {
  beforeEach(() => {
    vi.mocked(requireUser).mockResolvedValue({ user: TEST_USER as never });
    vi.mocked(getDashboardSummary).mockResolvedValue(SUMMARY);
  });

  afterEach(() => {
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

  it("returns the dashboard summary from rag-api as JSON", async () => {
    const res = await GET();
    const body = await res.json();

    expect(res.status).toBe(200);
    expect(body).toEqual(SUMMARY);
    expect(getDashboardSummary).toHaveBeenCalledWith(TEST_USER.id);
  });

  it("includes the expected summary fields", async () => {
    const res = await GET();
    const body = await res.json();

    expect(body).toMatchObject({
      totalIncome: expect.any(Number),
      totalSpending: expect.any(Number),
      netSavings: expect.any(Number),
      documentCount: expect.any(Number),
      totalDocumentCount: expect.any(Number),
      transactionCount: expect.any(Number),
      categoryBreakdown: expect.any(Array),
    });
  });

  it("passes through the rag-api error status on failure", async () => {
    vi.mocked(getDashboardSummary).mockRejectedValue(new RagApiError(502, "boom"));

    const res = await GET();
    const body = await res.json();

    expect(res.status).toBe(502);
    expect(body).toEqual({ error: "Failed to load dashboard summary" });
  });
});
