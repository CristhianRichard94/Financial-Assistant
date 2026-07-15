import { NextRequest, NextResponse } from "next/server";
import { store } from "@/lib/store";
import { z } from "zod";

export async function GET() {
  return NextResponse.json(store.chat.list());
}

const sendMessageSchema = z.object({
  content: z.string().min(1).max(4000),
});

const ASSISTANT_RESPONSES = [
  "Based on your financial documents, I can see some interesting patterns. Your discretionary spending has decreased by 8% compared to last month, which is a great sign.",
  "Looking at your uploaded statements, your savings rate is approximately 34% of your income — well above the recommended 20%. Keep it up!",
  "I notice you have several recurring subscriptions totaling $215/month. Would you like me to highlight which ones you haven't used recently?",
  "Your grocery spending is about $340/month, which is within the average for your household size. Dining out adds another $180.",
  "Great question! Based on your current savings trajectory, you could reach a 6-month emergency fund in approximately 4 months.",
];

export async function POST(req: NextRequest) {
  const body = await req.json();
  const parsed = sendMessageSchema.safeParse(body);
  if (!parsed.success) {
    return NextResponse.json({ error: "Invalid message" }, { status: 400 });
  }
  const userMsg = store.chat.add("user", parsed.data.content);
  const reply = ASSISTANT_RESPONSES[Math.floor(Math.random() * ASSISTANT_RESPONSES.length)];
  const assistantMsg = store.chat.add("assistant", reply);
  return NextResponse.json({ userMessage: userMsg, assistantMessage: assistantMsg }, { status: 201 });
}
