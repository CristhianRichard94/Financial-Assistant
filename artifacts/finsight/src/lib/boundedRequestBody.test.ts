import { describe, it, expect } from "vitest";
import {
  BodyTooLargeError,
  boundRequestBody,
  contentLengthExceedsLimit,
} from "@/lib/boundedRequestBody";

describe("BodyTooLargeError", () => {
  it("formats the limit as whole megabytes in the message", () => {
    const err = new BodyTooLargeError(10 * 1024 * 1024);
    expect(err.message).toBe("Request body exceeds the 10MB size limit");
    expect(err.name).toBe("BodyTooLargeError");
  });

  it("rounds a non-round MB limit", () => {
    const err = new BodyTooLargeError(1.5 * 1024 * 1024);
    expect(err.message).toBe("Request body exceeds the 2MB size limit");
  });
});

describe("contentLengthExceedsLimit", () => {
  const limit = 1024;

  it("returns false when the content-length header is absent", () => {
    const req = new Request("http://localhost/upload");
    expect(contentLengthExceedsLimit(req, limit)).toBe(false);
  });

  it("returns false when content-length is under the limit", () => {
    const req = new Request("http://localhost/upload", {
      headers: { "content-length": "512" },
    });
    expect(contentLengthExceedsLimit(req, limit)).toBe(false);
  });

  it("returns false when content-length equals the limit exactly", () => {
    const req = new Request("http://localhost/upload", {
      headers: { "content-length": "1024" },
    });
    expect(contentLengthExceedsLimit(req, limit)).toBe(false);
  });

  it("returns true when content-length exceeds the limit", () => {
    const req = new Request("http://localhost/upload", {
      headers: { "content-length": "2048" },
    });
    expect(contentLengthExceedsLimit(req, limit)).toBe(true);
  });

  it("returns false when content-length is not a parseable number", () => {
    const req = new Request("http://localhost/upload", {
      headers: { "content-length": "not-a-number" },
    });
    expect(contentLengthExceedsLimit(req, limit)).toBe(false);
  });

  it("returns false when content-length is negative", () => {
    const req = new Request("http://localhost/upload", {
      headers: { "content-length": "-5" },
    });
    expect(contentLengthExceedsLimit(req, limit)).toBe(false);
  });
});

function makeStreamedRequest(chunks: Uint8Array[]): Request {
  const stream = new ReadableStream<Uint8Array>({
    start(controller) {
      for (const chunk of chunks) {
        controller.enqueue(chunk);
      }
      controller.close();
    },
  });
  return new Request("http://localhost/upload", {
    method: "POST",
    body: stream,
    duplex: "half",
  } as RequestInit & { duplex: "half" });
}

async function readAll(req: Request): Promise<Uint8Array[]> {
  const reader = req.body!.getReader();
  const chunks: Uint8Array[] = [];
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    chunks.push(value);
  }
  return chunks;
}

describe("boundRequestBody", () => {
  it("returns the original request unchanged when there is no body", () => {
    const req = new Request("http://localhost/upload", { method: "GET" });
    const bounded = boundRequestBody(req, 1024);
    expect(bounded).toBe(req);
  });

  it("passes a body under the limit through unchanged", async () => {
    const payload = new TextEncoder().encode("hello world");
    const req = makeStreamedRequest([payload]);
    const bounded = boundRequestBody(req, 1024);

    const chunks = await readAll(bounded);
    const totalBytes = chunks.reduce((sum, c) => sum + c.byteLength, 0);
    expect(totalBytes).toBe(payload.byteLength);

    const text = new TextDecoder().decode(
      chunks.reduce((acc, c) => new Uint8Array([...acc, ...c]), new Uint8Array())
    );
    expect(text).toBe("hello world");
  });

  it("throws BodyTooLargeError once bytes read cross the limit", async () => {
    const chunk1 = new Uint8Array(600).fill(1);
    const chunk2 = new Uint8Array(600).fill(2);
    const req = makeStreamedRequest([chunk1, chunk2]);
    const limit = 1000;
    const bounded = boundRequestBody(req, limit);

    await expect(readAll(bounded)).rejects.toBeInstanceOf(BodyTooLargeError);
  });

  it("allows a body exactly at the limit", async () => {
    const payload = new Uint8Array(1024).fill(9);
    const req = makeStreamedRequest([payload]);
    const bounded = boundRequestBody(req, 1024);

    const chunks = await readAll(bounded);
    const totalBytes = chunks.reduce((sum, c) => sum + c.byteLength, 0);
    expect(totalBytes).toBe(1024);
  });
});
