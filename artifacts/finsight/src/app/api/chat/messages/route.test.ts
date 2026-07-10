import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { NextRequest, NextResponse } from "next/server";
import { GET, POST } from "@/app/api/chat/messages/route";

vi.mock("@/lib/ragApiClient", () => ({
  queryRag: vi.fn(),
}));

vi.mock("@/lib/auth/requireUser", () => ({
  requireUser: vi.fn(),
}));

vi.mock("@/lib/supabase/server", () => ({
  createClient: vi.fn(),
}));

import { queryRag } from "@/lib/ragApiClient";
import { requireUser } from "@/lib/auth/requireUser";
import { createClient } from "@/lib/supabase/server";

const FALLBACK_REPLY =
  "Sorry, I couldn't process that question right now. Please try again in a moment.";

const TEST_USER = { id: "user-1", email: "user@example.com" };

function makeRequest(body: unknown) {
  return new NextRequest("http://localhost/api/chat/messages", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

/** Builds a fake Supabase client covering only the query shapes this route
 * uses: `.from(...).select(...).order(...)` for GET, and
 * `.from(...).insert(...).select(...).single()` for POST. Each call to
 * `insert` consumes the next entry in `insertResults`, in call order (the
 * route always inserts the user message before the assistant reply). */
function makeSupabaseClient(options: {
  selectResult?: { data: unknown; error: unknown };
  insertResults?: Array<{ data: unknown; error: unknown }>;
}) {
  let insertCallIndex = 0;
  const from = vi.fn(() => ({
    select: vi.fn(() => ({
      order: vi.fn().mockResolvedValue(options.selectResult ?? { data: [], error: null }),
    })),
    insert: vi.fn(() => ({
      select: vi.fn(() => ({
        single: vi.fn().mockImplementation(async () => {
          const result = options.insertResults?.[insertCallIndex] ?? { data: null, error: null };
          insertCallIndex += 1;
          return result;
        }),
      })),
    })),
  }));
  return { from };
}

describe("GET /api/chat/messages", () => {
  afterEach(() => {
    vi.clearAllMocks();
  });

  it("returns 401 when there is no session", async () => {
    vi.mocked(requireUser).mockResolvedValue({
      response: NextResponse.json({ error: "Unauthorized" }, { status: 401 }),
    });

    const res = await GET();
    const body = await res.json();

    expect(res.status).toBe(401);
    expect(body).toEqual({ error: "Unauthorized" });
  });

  it("returns the current user's messages ordered by created_at", async () => {
    vi.mocked(requireUser).mockResolvedValue({ user: TEST_USER as never });
    const rows = [
      { id: "1", role: "assistant", content: "hi", created_at: "2024-01-01T00:00:00.000Z" },
      { id: "2", role: "user", content: "hello", created_at: "2024-01-01T00:01:00.000Z" },
    ];
    vi.mocked(createClient).mockResolvedValue(
      makeSupabaseClient({ selectResult: { data: rows, error: null } }) as never
    );

    const res = await GET();
    const body = await res.json();

    expect(res.status).toBe(200);
    expect(body).toEqual([
      { id: "1", role: "assistant", content: "hi", timestamp: "2024-01-01T00:00:00.000Z" },
      { id: "2", role: "user", content: "hello", timestamp: "2024-01-01T00:01:00.000Z" },
    ]);
  });

  it("returns 500 when the Supabase query fails", async () => {
    vi.mocked(requireUser).mockResolvedValue({ user: TEST_USER as never });
    vi.mocked(createClient).mockResolvedValue(
      makeSupabaseClient({ selectResult: { data: null, error: new Error("db down") } }) as never
    );
    const consoleErrorSpy = vi.spyOn(console, "error").mockImplementation(() => {});

    const res = await GET();

    expect(res.status).toBe(500);
    consoleErrorSpy.mockRestore();
  });
});

describe("POST /api/chat/messages", () => {
  beforeEach(() => {
    vi.mocked(requireUser).mockResolvedValue({ user: TEST_USER as never });
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it("returns 401 when there is no session", async () => {
    vi.mocked(requireUser).mockResolvedValue({
      response: NextResponse.json({ error: "Unauthorized" }, { status: 401 }),
    });

    const res = await POST(makeRequest({ content: "hello" }));

    expect(res.status).toBe(401);
    expect(queryRag).not.toHaveBeenCalled();
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

  it("stores the user message and the rag-api answer as the assistant reply, passing the user's id to queryRag", async () => {
    vi.mocked(queryRag).mockResolvedValue({
      answer: "You spent $50 on groceries.",
      sources: [],
    });
    vi.mocked(createClient).mockResolvedValue(
      makeSupabaseClient({
        insertResults: [
          {
            data: {
              id: "u1",
              role: "user",
              content: "How much did I spend on groceries?",
              created_at: "2024-01-01T00:00:00.000Z",
            },
            error: null,
          },
          {
            data: {
              id: "a1",
              role: "assistant",
              content: "You spent $50 on groceries.",
              created_at: "2024-01-01T00:00:01.000Z",
            },
            error: null,
          },
        ],
      }) as never
    );

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
    expect(queryRag).toHaveBeenCalledWith(
      "How much did I spend on groceries?",
      TEST_USER.id
    );
  });

  it("uses the fixed FALLBACK_REPLY when queryRag throws", async () => {
    vi.mocked(queryRag).mockRejectedValue(new Error("rag-api unavailable"));
    vi.mocked(createClient).mockResolvedValue(
      makeSupabaseClient({
        insertResults: [
          {
            data: {
              id: "u2",
              role: "user",
              content: "What's my balance?",
              created_at: "2024-01-01T00:00:00.000Z",
            },
            error: null,
          },
          {
            data: {
              id: "a2",
              role: "assistant",
              content: FALLBACK_REPLY,
              created_at: "2024-01-01T00:00:01.000Z",
            },
            error: null,
          },
        ],
      }) as never
    );
    const consoleErrorSpy = vi.spyOn(console, "error").mockImplementation(() => {});

    const res = await POST(makeRequest({ content: "What's my balance?" }));
    const body = await res.json();

    expect(res.status).toBe(201);
    expect(body.assistantMessage.content).toBe(FALLBACK_REPLY);

    consoleErrorSpy.mockRestore();
  });

  it("returns 500 when storing the user message fails", async () => {
    vi.mocked(createClient).mockResolvedValue(
      makeSupabaseClient({
        insertResults: [{ data: null, error: new Error("insert failed") }],
      }) as never
    );
    const consoleErrorSpy = vi.spyOn(console, "error").mockImplementation(() => {});

    const res = await POST(makeRequest({ content: "hello" }));

    expect(res.status).toBe(500);
    expect(queryRag).not.toHaveBeenCalled();

    consoleErrorSpy.mockRestore();
  });
});
