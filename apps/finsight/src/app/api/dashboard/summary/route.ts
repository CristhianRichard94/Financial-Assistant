import { NextResponse } from "next/server";
import { getDashboardSummary, RagApiError } from "@/lib/ragApiClient";
import { requireUser } from "@/lib/auth/requireUser";

export async function GET(request: Request) {
  const { user, response } = await requireUser();
  const requestId = request.headers.get("x-request-id") ?? "-";
  if (!user) return response;

  try {
    const summary = await getDashboardSummary(user.id, requestId);
    return NextResponse.json(summary);
  } catch (error) {
    console.error(`[${requestId}] Failed to load dashboard summary via rag-api:`, error);
    const status = error instanceof RagApiError ? error.status : 500;
    return NextResponse.json({ error: "Failed to load dashboard summary" }, { status });
  }
}
