import { NextRequest, NextResponse } from "next/server";
import { deleteDocument, RagApiError } from "@/lib/ragApiClient";

export async function DELETE(
  _req: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  const { id } = await params;
  try {
    await deleteDocument(id);
    return new NextResponse(null, { status: 204 });
  } catch (error) {
    if (error instanceof RagApiError && error.status === 404) {
      return NextResponse.json({ error: "Document not found" }, { status: 404 });
    }
    console.error("Failed to delete document via rag-api:", error);
    return NextResponse.json({ error: "Failed to delete document" }, { status: 500 });
  }
}
