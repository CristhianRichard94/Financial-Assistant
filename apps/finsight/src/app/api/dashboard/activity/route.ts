import { NextResponse } from "next/server";
import { getDashboardActivity, RagApiError } from "@/lib/ragApiClient";
import { requireUser } from "@/lib/auth/requireUser";

export async function GET(request: Request) {
  const { user, response } = await requireUser();
  if (!user) return response;

  const requestId = request.headers.get("x-request-id") ?? "-";

  try {
    const activity = await getDashboardActivity(user.id, requestId);
    return NextResponse.json(activity);
  } catch (error) {
    console.error(`[${requestId}] Failed to load recent activity via rag-api:`, error);
    const status = error instanceof RagApiError ? error.status : 500;
    return NextResponse.json({ error: "Failed to load recent activity" }, { status });
  }
}
