/**
 * Streaming defense against oversized request bodies for Next.js Route
 * Handlers.
 *
 * `req.formData()` (and `req.json()`, `req.text()`, etc.) fully buffer the
 * request body into memory before any application-level size check can run.
 * Unlike Server Actions, Route Handlers have no built-in `bodySizeLimit`
 * config, so a handler that just does `await req.formData()` and checks the
 * parsed file's size afterwards is vulnerable to a memory-exhaustion DoS: a
 * client can send an arbitrarily large multipart body and the whole thing
 * gets buffered before the size check ever runs.
 *
 * This mirrors the two-layer defense already used by the Python rag-api
 * service (see services/rag-api/rag_api/middleware.py and
 * services/rag-api/rag_api/routes/documents.py):
 *
 *  1. `contentLengthExceedsLimit` - a cheap check of the declared
 *     `Content-Length` header, letting the caller reject before the body is
 *     touched at all.
 *  2. `boundRequestBody` - wraps the request's `ReadableStream` body in a
 *     byte-counting stream that errors as soon as the cumulative bytes read
 *     exceed the limit. This is the authoritative bound: `Content-Length`
 *     can be forged or absent entirely (e.g. chunked transfer encoding), but
 *     the byte count of what's actually read off the stream cannot lie.
 */

export class BodyTooLargeError extends Error {
  constructor(limitBytes: number) {
    super(`Request body exceeds the ${(limitBytes / (1024 * 1024)).toFixed(0)}MB size limit`);
    this.name = "BodyTooLargeError";
  }
}

/**
 * Cheap first-pass check based purely on the declared `Content-Length`
 * header, without reading any part of the body. Returns `true` only when the
 * header is present, parseable, and exceeds `limitBytes`.
 *
 * A missing or unparseable header is NOT treated as a rejection here -
 * `Content-Length` can legitimately be absent (e.g. chunked transfer
 * encoding), and that case is covered by the streaming enforcement in
 * `boundRequestBody` instead.
 */
export function contentLengthExceedsLimit(req: Request, limitBytes: number): boolean {
  const header = req.headers.get("content-length");
  if (header === null) {
    return false;
  }
  const declaredBytes = Number(header);
  if (!Number.isFinite(declaredBytes) || declaredBytes < 0) {
    return false;
  }
  return declaredBytes > limitBytes;
}

/**
 * Returns a new `Request` whose body stream errors as soon as more than
 * `limitBytes` bytes have been read off it. This guarantees that any
 * consumer of the returned request's body (e.g. `.formData()`) can never
 * buffer more than ~`limitBytes` (plus at most one chunk's worth of
 * overshoot) into memory before the rejection happens - the full body is
 * never assembled in memory for an oversized request.
 *
 * If the request has no body (e.g. no bytes to stream), the original
 * request is returned unchanged.
 */
export function boundRequestBody(req: Request, limitBytes: number): Request {
  const body = req.body;
  if (!body) {
    return req;
  }

  const reader = body.getReader();
  let bytesRead = 0;

  const boundedStream = new ReadableStream<Uint8Array>({
    async pull(controller) {
      const { done, value } = await reader.read();
      if (done) {
        controller.close();
        return;
      }

      bytesRead += value.byteLength;
      if (bytesRead > limitBytes) {
        // Deliberately do NOT call `reader.cancel()` here: on some body-stream
        // implementations (e.g. a Request constructed from a FormData body),
        // cancelling the underlying reader immediately after erroring this
        // stream races with the source's own internal enqueue and produces an
        // unhandled promise rejection ("ReadableStream is already closed"),
        // which crashes the whole Node process with no global handler
        // installed. Calling `controller.error()` alone is sufficient to
        // reject any pending/future reads on this stream; the underlying
        // reader is left to be garbage-collected/closed by its own source
        // once it stops being pulled from.
        controller.error(new BodyTooLargeError(limitBytes));
        return;
      }

      controller.enqueue(value);
    },
    cancel(reason) {
      return reader.cancel(reason);
    },
  });

  const init: RequestInit & { duplex: "half" } = {
    method: req.method,
    headers: req.headers,
    body: boundedStream,
    // Node's fetch implementation requires `duplex: "half"` whenever the
    // request body is a stream. This option isn't part of the TS DOM
    // `RequestInit` type yet, hence the intersection type above.
    duplex: "half",
  };

  return new Request(req.url, init);
}
