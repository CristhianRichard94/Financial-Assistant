import { describe, it, expect } from "vitest";
import { GET } from "@/app/api/dashboard/summary/route";
import { store } from "@/lib/store";

describe("GET /api/dashboard/summary", () => {
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
