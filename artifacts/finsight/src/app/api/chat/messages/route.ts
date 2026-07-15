import { NextRequest, NextResponse } from "next/server";
import { z } from "zod";
import { queryRag } from "@/lib/ragApiClient";
import { requireUser } from "@/lib/auth/requireUser";
import { createClient } from "@/lib/supabase/server";
import type { ChatMessage } from "@/lib/store";

interface ChatMessageRow {
  id: string;
  role: "user" | "assistant";
  content: string;
  created_at: string;
}

function toChatMessage(row: ChatMessageRow): ChatMessage {
  return { id: row.id, role: row.role, content: row.content, timestamp: row.created_at };
}

export async function GET() {
  const { user, response } = await requireUser();
  if (!user) return response;

  const supabase = await createClient();

  // No explicit `.eq("user_id", ...)` filter here on purpose: this request
  // uses the caller's own session (anon key + cookies), not a service-role
  // key, so the RLS policies on `chat_messages` (see
  // services/rag-pipeline/sql/009_create_chat_messages_table.sql) are the
  // actual access control scoping this select to the current user's rows -
  // unlike rag-api, which uses a service-role key plus explicit filtering.
  const { data, error } = await supabase
    .from("chat_messages")
    .select("id, role, content, created_at")
    .order("created_at", { ascending: true });

  if (error) {
    console.error("Failed to load chat messages:", error);
    return NextResponse.json({ error: "Failed to load messages" }, { status: 500 });
  }

  return NextResponse.json((data ?? []).map(toChatMessage));
}

const sendMessageSchema = z.object({
  content: z.string().min(1).max(4000),
});

const FALLBACK_REPLY =
  "Sorry, I couldn't process that question right now. Please try again in a moment.";

export async function POST(req: NextRequest) {
  const { user, response } = await requireUser();
  if (!user) return response;

  const body = await req.json();
  const parsed = sendMessageSchema.safeParse(body);
  if (!parsed.success) {
    return NextResponse.json({ error: "Invalid message" }, { status: 400 });
  }

  const supabase = await createClient();

  const { data: userRow, error: userInsertError } = await supabase
    .from("chat_messages")
    .insert({ user_id: user.id, role: "user", content: parsed.data.content })
    .select("id, role, content, created_at")
    .single();

  if (userInsertError || !userRow) {
    console.error("Failed to store user chat message:", userInsertError);
    return NextResponse.json({ error: "Failed to send message" }, { status: 500 });
  }

  let replyContent = FALLBACK_REPLY;
  try {
    const result = await queryRag(parsed.data.content, user.id);
    replyContent = result.answer;
  } catch (error) {
    console.error("Failed to query rag-api for chat reply:", error);
  }

  const { data: assistantRow, error: assistantInsertError } = await supabase
    .from("chat_messages")
    .insert({ user_id: user.id, role: "assistant", content: replyContent })
    .select("id, role, content, created_at")
    .single();

  if (assistantInsertError || !assistantRow) {
    console.error("Failed to store assistant chat message:", assistantInsertError);
    return NextResponse.json({ error: "Failed to send message" }, { status: 500 });
  }

  return NextResponse.json(
    { userMessage: toChatMessage(userRow), assistantMessage: toChatMessage(assistantRow) },
    { status: 201 }
  );
}
