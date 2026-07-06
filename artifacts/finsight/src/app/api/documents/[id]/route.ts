import { NextRequest, NextResponse } from "next/server";
import { store } from "@/lib/store";

export async function DELETE(
  _req: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  const { id } = await params;
  const deleted = store.documents.delete(id);
  if (!deleted) {
    return NextResponse.json({ error: "Document not found" }, { status: 404 });
  }
  return new NextResponse(null, { status: 204 });
}
