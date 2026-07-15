import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { NextResponse } from "next/server";
import { GET } from "@/app/api/dashboard/summary/route";
import { store } from "@/lib/store";

vi.mock("@/lib/auth/requireUser", () => ({
  requireUser: vi.fn(),
}));

import { requireUser } from "@/lib/auth/requireUser";

const TEST_USER = { id: "user-1", email: "user@example.com" };

describe("GET /api/dashboard/summary", () => {
  beforeEach(() => {
    vi.mocked(requireUser).mockResolvedValue({ user: TEST_USER as never });
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

  it("returns the store's dashboard summary as JSON", async () => {
    const res = await GET();
    const body = await res.json();

    expect(res.status).toBe(200);
    expect(body).toEqual(store.dashboard.summary());
  });

  it("includes the expected summary fields", async () => {
    const res = await GET();
    const body = await res.json();

    expect(body).toMatchObject({
      totalIncome: expect.any(Number),
      totalSpending: expect.any(Number),
      netSavings: expect.any(Number),
      documentCount: expect.any(Number),
      categoryBreakdown: expect.any(Array),
    });
  });
});
