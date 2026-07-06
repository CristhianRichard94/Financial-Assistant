import { NextRequest, NextResponse } from "next/server";
import { listDocuments, RagApiError, uploadDocument } from "@/lib/ragApiClient";

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

export async function POST(req: NextRequest) {
  const formData = await req.formData();
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
