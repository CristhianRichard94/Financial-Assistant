import { NextResponse } from "next/server";
import { HealthCheckResponse } from "@workspace/api-zod";

export async function GET() {
  const data = HealthCheckResponse.parse({ status: "ok" });
  return NextResponse.json(data);
}
