import { NextRequest, NextResponse } from "next/server";
import { store } from "@/lib/store";
import { z } from "zod";
import { queryRag } from "@/lib/ragApiClient";

export async function GET() {
  return NextResponse.json(store.chat.list());
}

const sendMessageSchema = z.object({
  content: z.string().min(1).max(4000),
});

const FALLBACK_REPLY =
  "Sorry, I couldn't process that question right now. Please try again in a moment.";

export async function POST(req: NextRequest) {
  const body = await req.json();
  const parsed = sendMessageSchema.safeParse(body);
  if (!parsed.success) {
    return NextResponse.json({ error: "Invalid message" }, { status: 400 });
  }

  const userMsg = store.chat.add("user", parsed.data.content);

  let replyContent = FALLBACK_REPLY;
  try {
    const result = await queryRag(parsed.data.content);
    replyContent = result.answer;
  } catch (error) {
    console.error("Failed to query rag-api for chat reply:", error);
  }

  const assistantMsg = store.chat.add("assistant", replyContent);
  return NextResponse.json({ userMessage: userMsg, assistantMessage: assistantMsg }, { status: 201 });
}
