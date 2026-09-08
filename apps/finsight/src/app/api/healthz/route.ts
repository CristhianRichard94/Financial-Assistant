import { NextResponse } from "next/server";
import { z } from "zod";

const HealthCheckResponse = z.object({ status: z.literal("ok") });

export async function GET() {
  const data = HealthCheckResponse.parse({ status: "ok" });
  return NextResponse.json(data);
}
