import { describe, it, expect, vi, afterEach } from "vitest";
import { NextRequest } from "next/server";
import { DELETE } from "@/app/api/documents/[id]/route";
import { RagApiError } from "@/lib/ragApiClient";

vi.mock("@/lib/ragApiClient", async () => {
  const actual = await vi.importActual<typeof import("@/lib/ragApiClient")>(
    "@/lib/ragApiClient"
  );
  return {
    ...actual,
    deleteDocument: vi.fn(),
  };
});

import { deleteDocument } from "@/lib/ragApiClient";

function makeRequest(id: string) {
  const req = new NextRequest(`http://localhost/api/documents/${id}`, { method: "DELETE" });
  return { req, params: Promise.resolve({ id }) };
}

describe("DELETE /api/documents/[id]", () => {
  afterEach(() => {
    vi.clearAllMocks();
  });

  it("returns 204 on successful deletion", async () => {
    vi.mocked(deleteDocument).mockResolvedValue(undefined);
    const { req, params } = makeRequest("abc123");

    const res = await DELETE(req, { params });

    expect(res.status).toBe(204);
    expect(deleteDocument).toHaveBeenCalledWith("abc123");
  });

  it("maps a 404 RagApiError to a 404 response with a friendly message", async () => {
    vi.mocked(deleteDocument).mockRejectedValue(new RagApiError(404, "not found"));
    const { req, params } = makeRequest("missing");

    const res = await DELETE(req, { params });
    const body = await res.json();

    expect(res.status).toBe(404);
    expect(body).toEqual({ error: "Document not found" });
  });

  it("maps a non-404 RagApiError to a 500 response", async () => {
    vi.mocked(deleteDocument).mockRejectedValue(new RagApiError(500, "server error"));
    const { req, params } = makeRequest("abc123");

    const res = await DELETE(req, { params });
    const body = await res.json();

    expect(res.status).toBe(500);
    expect(body).toEqual({ error: "Failed to delete document" });
  });

  it("maps a non-RagApiError failure to a 500 response", async () => {
    vi.mocked(deleteDocument).mockRejectedValue(new Error("network down"));
    const { req, params } = makeRequest("abc123");

    const res = await DELETE(req, { params });

    expect(res.status).toBe(500);
  });
});
