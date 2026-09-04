import { NextRequest, NextResponse } from "next/server";
import { deleteDocument, RagApiError } from "@/lib/ragApiClient";
import { requireUser } from "@/lib/auth/requireUser";

export async function DELETE(
  _req: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  const { user, response } = await requireUser();
  if (!user) return response;

  const requestId = _req.headers.get("x-request-id");

  const { id } = await params;
  try {
    await deleteDocument(id, user.id);
    return new NextResponse(null, { status: 204 });
  } catch (error) {
    if (error instanceof RagApiError && error.status === 404) {
      return NextResponse.json({ error: "document_not_found" }, { status: 404 });
    }
    console.error(`[${requestId}] Failed to delete document via rag-api:`, error);
    return NextResponse.json({ error: "delete_document_failed" }, { status: 500 });
  }
}
