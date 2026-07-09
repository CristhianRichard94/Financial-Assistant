import { describe, it, expect } from "vitest";
import { GET } from "@/app/api/healthz/route";

describe("GET /api/healthz", () => {
  it("returns the server health status as JSON", async () => {
    const res = await GET();
    const body = await res.json();

    expect(res.status).toBe(200);
    expect(body).toEqual({ status: "ok" });
  });
});
