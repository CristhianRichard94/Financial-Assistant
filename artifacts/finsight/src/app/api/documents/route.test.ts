// @vitest-environment node
//
// This route handler test builds a real multipart/form-data `Request` body
// (to exercise the upload size-validation logic against actual streamed
// bytes). Under the jsdom test environment (the project-wide default, since
// most components need a DOM), the global `File`/`Blob` constructors are
// jsdom's own implementation - a *different* class than the one Node's
// built-in fetch/undici implementation expects when serializing/parsing
// multipart bodies, which silently corrupts the parsed file part (it comes
// back as a plain string instead of a File). Running this file under the
// plain "node" environment instead avoids that mismatch, since this route
// handler doesn't touch the DOM anyway.
import { describe, it, expect, vi, afterEach } from "vitest";
import { NextRequest } from "next/server";
import { GET, POST } from "@/app/api/documents/route";
import { RagApiError } from "@/lib/ragApiClient";

vi.mock("@/lib/ragApiClient", async () => {
  const actual = await vi.importActual<typeof import("@/lib/ragApiClient")>(
    "@/lib/ragApiClient"
  );
  return {
    ...actual,
    listDocuments: vi.fn(),
    uploadDocument: vi.fn(),
  };
});

import { listDocuments, uploadDocument } from "@/lib/ragApiClient";

const MAX_UPLOAD_BYTES = 10 * 1024 * 1024;

function makeUploadRequest(options: {
  formData?: FormData;
  contentLength?: number;
  body?: ReadableStream<Uint8Array> | null;
}): NextRequest {
  const headers: Record<string, string> = {};
  let body: BodyInit | undefined;

  if (options.formData) {
    body = options.formData;
  } else if (options.body !== undefined) {
    body = options.body ?? undefined;
  }

  if (options.contentLength !== undefined) {
    headers["content-length"] = String(options.contentLength);
  }

  const init: RequestInit & { duplex?: "half" } = {
    method: "POST",
    headers,
    body,
  };
  if (body instanceof ReadableStream) {
    init.duplex = "half";
  }

  // `NextRequest`'s own `RequestInit` type (re-exported from Next's internal
  // request module) is slightly stricter than the DOM lib's `RequestInit`
  // (e.g. `signal` excludes `null`), so cast through the constructor's own
  // parameter type rather than the DOM one.
  return new NextRequest(
    "http://localhost/api/documents",
    init as ConstructorParameters<typeof NextRequest>[1]
  );
}

describe("GET /api/documents", () => {
  afterEach(() => {
    vi.clearAllMocks();
  });

  it("returns documents from rag-api on success", async () => {
    const docs = [{ id: "1", name: "a.pdf" }];
    vi.mocked(listDocuments).mockResolvedValue(docs as never);

    const res = await GET();
    const body = await res.json();

    expect(res.status).toBe(200);
    expect(body).toEqual(docs);
  });

  it("maps a RagApiError status to the response status", async () => {
    vi.mocked(listDocuments).mockRejectedValue(new RagApiError(503, "unavailable"));

    const res = await GET();
    const body = await res.json();

    expect(res.status).toBe(503);
    expect(body).toEqual({ error: "Failed to list documents" });
  });

  it("falls back to a 500 status for a non-RagApiError failure", async () => {
    vi.mocked(listDocuments).mockRejectedValue(new Error("boom"));

    const res = await GET();

    expect(res.status).toBe(500);
  });
});

describe("POST /api/documents", () => {
  afterEach(() => {
    vi.clearAllMocks();
  });

  it("returns 400 when no file is provided", async () => {
    const form = new FormData();
    const req = makeUploadRequest({ formData: form });

    const res = await POST(req);
    const body = await res.json();

    expect(res.status).toBe(400);
    expect(body).toEqual({ error: "No file provided" });
  });

  it("returns 400 when the declared content-length exceeds the limit (layer 1 rejection)", async () => {
    const req = makeUploadRequest({
      formData: new FormData(),
      contentLength: MAX_UPLOAD_BYTES + 100 * 1024 * 1024,
    });

    const res = await POST(req);
    const body = await res.json();

    expect(res.status).toBe(400);
    expect(body).toEqual({ error: "File exceeds 10MB limit" });
    expect(uploadDocument).not.toHaveBeenCalled();
  });

  it("returns 400 when the file itself exceeds MAX_UPLOAD_BYTES", async () => {
    const form = new FormData();
    const oversizedFile = new File([new Uint8Array(MAX_UPLOAD_BYTES + 1)], "big.pdf", {
      type: "application/pdf",
    });
    form.append("file", oversizedFile);
    const req = makeUploadRequest({ formData: form });

    const res = await POST(req);
    const body = await res.json();

    expect(res.status).toBe(400);
    expect(body).toEqual({ error: "File exceeds 10MB limit" });
    expect(uploadDocument).not.toHaveBeenCalled();
  });

  it("rejects a body whose actual streamed bytes exceed the limit (layer 2, bounded stream)", async () => {
    // Simulate a request with no (forged/absent) Content-Length but whose
    // actual body stream exceeds MAX_REQUEST_BODY_BYTES once read.
    const hugeChunk = new Uint8Array(15 * 1024 * 1024).fill(1);
    const stream = new ReadableStream<Uint8Array>({
      start(controller) {
        controller.enqueue(hugeChunk);
        controller.close();
      },
    });
    const req = makeUploadRequest({ body: stream });

    const res = await POST(req);
    const body = await res.json();

    expect(res.status).toBe(400);
    expect(body).toEqual({ error: "File exceeds 10MB limit" });
  });

  it("uploads successfully via the mocked rag-api client", async () => {
    const form = new FormData();
    const file = new File(["hello"], "small.pdf", { type: "application/pdf" });
    form.append("file", file);
    const req = makeUploadRequest({ formData: form });

    const createdDoc = { id: "1", name: "small.pdf", status: "pending" };
    vi.mocked(uploadDocument).mockResolvedValue(createdDoc as never);

    const res = await POST(req);
    const body = await res.json();

    expect(res.status).toBe(201);
    expect(body).toEqual(createdDoc);
    expect(uploadDocument).toHaveBeenCalledTimes(1);
  });

  it("maps a RagApiError from uploadDocument to the response status", async () => {
    const form = new FormData();
    const file = new File(["hello"], "small.pdf", { type: "application/pdf" });
    form.append("file", file);
    const req = makeUploadRequest({ formData: form });

    vi.mocked(uploadDocument).mockRejectedValue(new RagApiError(502, "bad gateway"));

    const res = await POST(req);
    const body = await res.json();

    expect(res.status).toBe(502);
    expect(body).toEqual({ error: "Upload failed" });
  });
});
