import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import {
  RagApiError,
  listDocuments,
  uploadDocument,
  deleteDocument,
  queryRag,
} from "@/lib/ragApiClient";

const BASE_URL = "http://localhost:8000";
const INTERNAL_KEY = "test-key";

function stubEnv() {
  vi.stubEnv("RAG_API_BASE_URL", BASE_URL);
  vi.stubEnv("RAG_API_INTERNAL_KEY", INTERNAL_KEY);
}

function mockFetchOnce(response: Partial<Response>) {
  const fetchMock = vi.fn().mockResolvedValue(response);
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

describe("ragApiClient env var validation", () => {
  afterEach(() => {
    vi.unstubAllEnvs();
    vi.unstubAllGlobals();
  });

  it("throws when RAG_API_BASE_URL is not set", async () => {
    vi.stubEnv("RAG_API_BASE_URL", "");
    vi.stubEnv("RAG_API_INTERNAL_KEY", INTERNAL_KEY);

    await expect(listDocuments()).rejects.toThrow(/RAG_API_BASE_URL is not set/);
  });

  it("throws when RAG_API_INTERNAL_KEY is not set", async () => {
    vi.stubEnv("RAG_API_BASE_URL", BASE_URL);
    vi.stubEnv("RAG_API_INTERNAL_KEY", "");

    await expect(listDocuments()).rejects.toThrow(/RAG_API_INTERNAL_KEY is not set/);
  });
});

describe("ragApiClient requests", () => {
  beforeEach(() => {
    stubEnv();
  });

  afterEach(() => {
    vi.unstubAllEnvs();
    vi.unstubAllGlobals();
  });

  describe("listDocuments", () => {
    it("returns documents on success", async () => {
      const docs = [{ id: "1", name: "a.pdf" }];
      const fetchMock = mockFetchOnce({ ok: true, json: async () => docs });

      const result = await listDocuments();

      expect(result).toEqual(docs);
      expect(fetchMock).toHaveBeenCalledWith(
        `${BASE_URL}/documents`,
        expect.objectContaining({
          headers: { "X-Internal-Api-Key": INTERNAL_KEY },
        })
      );
    });

    it("throws RagApiError using the JSON detail field on failure", async () => {
      mockFetchOnce({
        ok: false,
        status: 500,
        statusText: "Server Error",
        json: async () => ({ detail: "db down" }),
      });

      await expect(listDocuments()).rejects.toMatchObject({
        name: "RagApiError",
        status: 500,
        message: "Failed to list documents: db down",
      });
    });

    it("falls back to the JSON error field when detail is absent", async () => {
      mockFetchOnce({
        ok: false,
        status: 400,
        statusText: "Bad Request",
        json: async () => ({ error: "bad input" }),
      });

      await expect(listDocuments()).rejects.toMatchObject({
        message: "Failed to list documents: bad input",
      });
    });

    it("falls back to res.statusText when the body has neither detail nor error", async () => {
      mockFetchOnce({
        ok: false,
        status: 502,
        statusText: "Bad Gateway",
        json: async () => ({}),
      });

      await expect(listDocuments()).rejects.toMatchObject({
        message: "Failed to list documents: Bad Gateway",
      });
    });

    it("falls back to res.statusText when the body is not valid JSON", async () => {
      mockFetchOnce({
        ok: false,
        status: 503,
        statusText: "Service Unavailable",
        json: async () => {
          throw new Error("invalid JSON");
        },
      });

      await expect(listDocuments()).rejects.toMatchObject({
        message: "Failed to list documents: Service Unavailable",
      });
    });
  });

  describe("uploadDocument", () => {
    it("posts the form data and returns the created document", async () => {
      const doc = { id: "2", name: "b.csv" };
      const fetchMock = mockFetchOnce({ ok: true, json: async () => doc });
      const form = new FormData();

      const result = await uploadDocument(form);

      expect(result).toEqual(doc);
      expect(fetchMock).toHaveBeenCalledWith(
        `${BASE_URL}/upload`,
        expect.objectContaining({
          method: "POST",
          headers: { "X-Internal-Api-Key": INTERNAL_KEY },
          body: form,
        })
      );
    });

    it("throws RagApiError on failure", async () => {
      mockFetchOnce({
        ok: false,
        status: 413,
        statusText: "Payload Too Large",
        json: async () => ({ detail: "file too large" }),
      });

      await expect(uploadDocument(new FormData())).rejects.toBeInstanceOf(RagApiError);
    });
  });

  describe("deleteDocument", () => {
    it("issues a DELETE request", async () => {
      const fetchMock = mockFetchOnce({ ok: true, json: async () => ({}) });

      await deleteDocument("abc");

      expect(fetchMock).toHaveBeenCalledWith(
        `${BASE_URL}/documents/abc`,
        expect.objectContaining({
          method: "DELETE",
          headers: { "X-Internal-Api-Key": INTERNAL_KEY },
        })
      );
    });

    it("throws RagApiError with a 404 status when the document is missing", async () => {
      mockFetchOnce({
        ok: false,
        status: 404,
        statusText: "Not Found",
        json: async () => ({ detail: "not found" }),
      });

      await expect(deleteDocument("missing")).rejects.toMatchObject({
        name: "RagApiError",
        status: 404,
      });
    });
  });

  describe("queryRag", () => {
    it("posts the question and returns the answer", async () => {
      const queryResult = { answer: "You spent $100", sources: [] };
      const fetchMock = mockFetchOnce({ ok: true, json: async () => queryResult });

      const result = await queryRag("How much did I spend?");

      expect(result).toEqual(queryResult);
      expect(fetchMock).toHaveBeenCalledWith(
        `${BASE_URL}/query`,
        expect.objectContaining({
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "X-Internal-Api-Key": INTERNAL_KEY,
          },
          body: JSON.stringify({ question: "How much did I spend?" }),
        })
      );
    });

    it("throws RagApiError on failure", async () => {
      mockFetchOnce({
        ok: false,
        status: 500,
        statusText: "Server Error",
        json: async () => ({}),
      });

      await expect(queryRag("question")).rejects.toBeInstanceOf(RagApiError);
    });
  });
});
