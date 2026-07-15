import { NextRequest, NextResponse } from "next/server";
import { listDocuments, RagApiError, uploadDocument } from "@/lib/ragApiClient";
import {
  BodyTooLargeError,
  boundRequestBody,
  contentLengthExceedsLimit,
} from "@/lib/boundedRequestBody";

export async function GET() {
  try {
    const documents = await listDocuments();
    return NextResponse.json(documents);
  } catch (error) {
    console.error("Failed to list documents via rag-api:", error);
    const status = error instanceof RagApiError ? error.status : 500;
    return NextResponse.json({ error: "Failed to list documents" }, { status });
  }
}

const MAX_UPLOAD_BYTES = 10 * 1024 * 1024;

// Multipart encoding adds a boundary marker and per-part headers on top of
// the raw file bytes, so a compliant upload's overall request body is
// slightly larger than MAX_UPLOAD_BYTES. This mirrors
// `_MULTIPART_OVERHEAD_ALLOWANCE_BYTES` in the Python rag-api service
// (services/rag-api/rag_api/routes/documents.py).
const MULTIPART_OVERHEAD_ALLOWANCE_BYTES = 64 * 1024;
const MAX_REQUEST_BODY_BYTES = MAX_UPLOAD_BYTES + MULTIPART_OVERHEAD_ALLOWANCE_BYTES;

export async function POST(req: NextRequest) {
  // Layer 1: cheap rejection based on the declared Content-Length, before
  // the body is read at all. `req.formData()` has no built-in size limit in
  // a Route Handler, so without this an oversized request would otherwise
  // be fully buffered into memory before any check could run.
  if (contentLengthExceedsLimit(req, MAX_REQUEST_BODY_BYTES)) {
    return NextResponse.json({ error: "File exceeds 10MB limit" }, { status: 400 });
  }

  // Layer 2: Content-Length can be forged or absent (e.g. chunked transfer
  // encoding), so also bound the body as it's actually streamed off the
  // network. This guarantees the body is never fully assembled in memory
  // for an oversized request, regardless of what the header claimed.
  const boundedReq = boundRequestBody(req, MAX_REQUEST_BODY_BYTES);

  let formData: FormData;
  try {
    formData = await boundedReq.formData();
  } catch (error) {
    if (error instanceof BodyTooLargeError) {
      return NextResponse.json({ error: "File exceeds 10MB limit" }, { status: 400 });
    }
    console.error("Failed to parse upload request body:", error);
    return NextResponse.json({ error: "Invalid upload" }, { status: 400 });
  }

  const file = formData.get("file") as File | null;
  if (!file) {
    return NextResponse.json({ error: "No file provided" }, { status: 400 });
  }

  if (file.size > MAX_UPLOAD_BYTES) {
    return NextResponse.json({ error: "File exceeds 10MB limit" }, { status: 400 });
  }

  try {
    const doc = await uploadDocument(formData);
    return NextResponse.json(doc, { status: 201 });
  } catch (error) {
    console.error("Failed to upload document via rag-api:", error);
    const status = error instanceof RagApiError ? error.status : 500;
    return NextResponse.json({ error: "Upload failed" }, { status });
  }
}
