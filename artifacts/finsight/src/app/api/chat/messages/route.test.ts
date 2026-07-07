import { describe, it, expect, vi, afterEach } from "vitest";
import { NextRequest } from "next/server";
import { GET, POST } from "@/app/api/chat/messages/route";
import { store } from "@/lib/store";

vi.mock("@/lib/ragApiClient", () => ({
  queryRag: vi.fn(),
}));

import { queryRag } from "@/lib/ragApiClient";

const FALLBACK_REPLY =
  "Sorry, I couldn't process that question right now. Please try again in a moment.";

function makeRequest(body: unknown) {
  return new NextRequest("http://localhost/api/chat/messages", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

describe("GET /api/chat/messages", () => {
  it("returns store.chat.list()", async () => {
    const res = await GET();
    const body = await res.json();

    expect(res.status).toBe(200);
    expect(body).toEqual(store.chat.list());
  });
});

describe("POST /api/chat/messages", () => {
  afterEach(() => {
    vi.clearAllMocks();
  });

  it("returns 400 for an invalid body (empty content)", async () => {
    const res = await POST(makeRequest({ content: "" }));
    const body = await res.json();

    expect(res.status).toBe(400);
    expect(body).toEqual({ error: "Invalid message" });
  });

  it("returns 400 when content is missing", async () => {
    const res = await POST(makeRequest({}));
    expect(res.status).toBe(400);
  });

  it("returns 400 when content exceeds the max length", async () => {
    const res = await POST(makeRequest({ content: "a".repeat(4001) }));
    expect(res.status).toBe(400);
  });

  it("stores the user message and the rag-api answer as the assistant reply", async () => {
    vi.mocked(queryRag).mockResolvedValue({
      answer: "You spent $50 on groceries.",
      sources: [],
    });

    const res = await POST(makeRequest({ content: "How much did I spend on groceries?" }));
    const body = await res.json();

    expect(res.status).toBe(201);
    expect(body.userMessage).toMatchObject({
      role: "user",
      content: "How much did I spend on groceries?",
    });
    expect(body.assistantMessage).toMatchObject({
      role: "assistant",
      content: "You spent $50 on groceries.",
    });
  });

  it("uses the fixed FALLBACK_REPLY when queryRag throws", async () => {
    vi.mocked(queryRag).mockRejectedValue(new Error("rag-api unavailable"));
    const consoleErrorSpy = vi.spyOn(console, "error").mockImplementation(() => {});

    const res = await POST(makeRequest({ content: "What's my balance?" }));
    const body = await res.json();

    expect(res.status).toBe(201);
    expect(body.assistantMessage.content).toBe(FALLBACK_REPLY);

    consoleErrorSpy.mockRestore();
  });
});
