import { NextResponse } from "next/server";
import { store } from "@/lib/store";
import { requireUser } from "@/lib/auth/requireUser";

export async function GET() {
  const { user, response } = await requireUser();
  if (!user) return response;

  return NextResponse.json(store.dashboard.activity());
}
