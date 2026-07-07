import { describe, it, expect, vi, afterEach } from "vitest";
import { apiFetch } from "@/lib/api";

describe("apiFetch", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("returns the parsed JSON body on success", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ hello: "world" }),
    });
    vi.stubGlobal("fetch", fetchMock);

    const result = await apiFetch<{ hello: string }>("/api/whatever");

    expect(result).toEqual({ hello: "world" });
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/whatever",
      expect.objectContaining({
        headers: expect.objectContaining({ "Content-Type": "application/json" }),
      })
    );
  });

  it("throws using the JSON error field on a non-ok response", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: false,
      statusText: "Bad Request",
      json: async () => ({ error: "Something went wrong" }),
    });
    vi.stubGlobal("fetch", fetchMock);

    await expect(apiFetch("/api/whatever")).rejects.toThrow("Something went wrong");
  });

  it("falls back to res.statusText when the error body is not JSON", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: false,
      statusText: "Internal Server Error",
      json: async () => {
        throw new Error("not JSON");
      },
    });
    vi.stubGlobal("fetch", fetchMock);

    await expect(apiFetch("/api/whatever")).rejects.toThrow("Internal Server Error");
  });

  // NOTE (pre-existing bug, not introduced by this test suite): `apiFetch`
  // builds its fetch options as `{ headers: { "Content-Type": ..., ...options?.headers },
  // ...options }`. Because `...options` is spread *after* the computed
  // `headers` key, if the caller passes its own `headers`, that raw
  // (unmerged) object completely replaces the computed one - the default
  // `Content-Type: application/json` is silently dropped instead of being
  // merged alongside the caller's headers. This test documents the actual
  // current behavior; see PR/review notes for whether this should be fixed.
  it("caller-supplied headers replace (rather than merge with) the default Content-Type header", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({}),
    });
    vi.stubGlobal("fetch", fetchMock);

    await apiFetch("/api/whatever", { headers: { Authorization: "Bearer token" } });

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/whatever",
      expect.objectContaining({
        headers: { Authorization: "Bearer token" },
      })
    );
  });

  it("keeps the default Content-Type header when no custom headers are passed", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({}),
    });
    vi.stubGlobal("fetch", fetchMock);

    await apiFetch("/api/whatever");

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/whatever",
      expect.objectContaining({
        headers: { "Content-Type": "application/json" },
      })
    );
  });
});
