import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider, onlineManager } from "@tanstack/react-query";
import { ChatView } from "@/components/views/ChatView";
import type { ChatMessage, Document } from "@/lib/store";

vi.mock("sonner", () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
  },
}));

import { toast } from "sonner";

const processedDoc: Document = {
  id: "d1",
  name: "statement.pdf",
  type: "pdf",
  size: 1000,
  status: "processed",
  uploadedAt: "2025-05-01T00:00:00.000Z",
};

const seedMessages: ChatMessage[] = [
  {
    id: "m1",
    role: "assistant",
    content: "Hello! How can I help?",
    timestamp: "2025-05-01T00:00:00.000Z",
  },
];

function renderWithClient(ui: React.ReactElement) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(<QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>);
}

interface RouteConfig {
  ok: boolean;
  body: unknown;
}

function installFetchMock(routes: {
  messages: RouteConfig | RouteConfig[];
  documents?: RouteConfig;
  post?: RouteConfig | RouteConfig[];
  postDelayMs?: number;
}) {
  let messageCallCount = 0;
  let postCallCount = 0;
  const messagesQueue = Array.isArray(routes.messages) ? routes.messages : [routes.messages];
  const postQueue = routes.post
    ? Array.isArray(routes.post)
      ? routes.post
      : [routes.post]
    : [{ ok: true, body: {} }];

  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = typeof input === "string" ? input : input.toString();

    if (url.includes("/api/chat/messages") && (!init || init.method === undefined)) {
      const idx = Math.min(messageCallCount, messagesQueue.length - 1);
      const route = messagesQueue[idx];
      messageCallCount += 1;
      return { ok: route.ok, status: route.ok ? 200 : 500, json: async () => route.body } as Response;
    }
    if (url.includes("/api/chat/messages") && init?.method === "POST") {
      if (routes.postDelayMs) {
        await new Promise((resolve) => setTimeout(resolve, routes.postDelayMs));
      }
      const idx = Math.min(postCallCount, postQueue.length - 1);
      const route = postQueue[idx];
      postCallCount += 1;
      return { ok: route.ok, status: route.ok ? 201 : 500, json: async () => route.body } as Response;
    }
    if (url.includes("/api/documents")) {
      const route = routes.documents ?? { ok: true, body: [] };
      return { ok: route.ok, status: route.ok ? 200 : 500, json: async () => route.body } as Response;
    }
    return { ok: false, status: 404, json: async () => ({}) } as Response;
  });

  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

describe("ChatView", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    // Some tests flip the browser "online" state; restore it so it can't
    // leak into unrelated tests.
    onlineManager.setOnline(true);
  });

  it("shows a loading spinner while messages are loading", () => {
    vi.stubGlobal("fetch", vi.fn(() => new Promise(() => {})));

    const { container } = renderWithClient(<ChatView />);

    expect(container.querySelector(".animate-spin")).toBeInTheDocument();
  });

  it("shows an error state when messages fail to load", async () => {
    installFetchMock({ messages: { ok: false, body: {} } });

    renderWithClient(<ChatView />);

    await waitFor(() =>
      expect(screen.getByText("Couldn't load messages. Please try again.")).toBeInTheDocument()
    );
  });

  it("shows the empty state when there are no messages", async () => {
    installFetchMock({ messages: { ok: true, body: [] } });

    renderWithClient(<ChatView />);

    await waitFor(() => expect(screen.getByText("Welcome to FinSight")).toBeInTheDocument());
  });

  it("renders the populated message list", async () => {
    installFetchMock({ messages: { ok: true, body: seedMessages } });

    renderWithClient(<ChatView />);

    await waitFor(() => expect(screen.getByText("Hello! How can I help?")).toBeInTheDocument());
  });

  it("shows the no-documents callout when there are no processed documents", async () => {
    installFetchMock({
      messages: { ok: true, body: seedMessages },
      documents: { ok: true, body: [] },
    });

    renderWithClient(<ChatView />);

    await waitFor(() =>
      expect(screen.getByText(/No processed documents yet\./)).toBeInTheDocument()
    );
  });

  it("hides the no-documents callout once a processed document exists", async () => {
    installFetchMock({
      messages: { ok: true, body: seedMessages },
      documents: { ok: true, body: [processedDoc] },
    });

    renderWithClient(<ChatView />);

    await waitFor(() => expect(screen.getByText("Hello! How can I help?")).toBeInTheDocument());
    expect(screen.queryByText(/No processed documents yet\./)).not.toBeInTheDocument();
  });

  it("sends a message on Enter, shows the typing indicator, and refetches the list", async () => {
    const user = userEvent.setup();
    const newAssistantMsg: ChatMessage = {
      id: "m3",
      role: "assistant",
      content: "Here's your answer.",
      timestamp: "2025-05-01T00:05:00.000Z",
    };
    const userMsg: ChatMessage = {
      id: "m2",
      role: "user",
      content: "What did I spend?",
      timestamp: "2025-05-01T00:04:00.000Z",
    };

    const fetchMock = installFetchMock({
      messages: [
        { ok: true, body: seedMessages },
        { ok: true, body: [...seedMessages, userMsg, newAssistantMsg] },
      ],
      post: { ok: true, body: { userMessage: userMsg, assistantMessage: newAssistantMsg } },
      postDelayMs: 50,
    });

    renderWithClient(<ChatView />);

    await waitFor(() => expect(screen.getByText("Hello! How can I help?")).toBeInTheDocument());

    const textarea = screen.getByPlaceholderText(/Ask me/);
    await user.type(textarea, "What did I spend?");
    await user.keyboard("{Enter}");

    // While the POST mutation is pending, the typing indicator should show
    // and the textarea should have been cleared.
    await waitFor(() => {
      expect(document.querySelector(".animate-bounce")).toBeInTheDocument();
    });
    expect(textarea).toHaveValue("");

    await waitFor(() => {
      const postCall = fetchMock.mock.calls.find(
        (call) => call[1]?.method === "POST"
      );
      expect(postCall).toBeDefined();
    });

    const postCall = fetchMock.mock.calls.find((call) => call[1]?.method === "POST");
    expect(JSON.parse(postCall![1]!.body as string)).toEqual({ content: "What did I spend?" });

    await waitFor(() =>
      expect(screen.getByText("Here's your answer.")).toBeInTheDocument()
    );
  });

  it("keeps a failed message in its chronological position when a later send succeeds", async () => {
    const user = userEvent.setup();
    const now = Date.now();
    const secondUserMsg: ChatMessage = {
      id: "m2",
      role: "user",
      content: "second-msg",
      timestamp: new Date(now + 60_000).toISOString(),
    };
    const assistantReply: ChatMessage = {
      id: "m3",
      role: "assistant",
      content: "Reply to second-msg.",
      timestamp: new Date(now + 61_000).toISOString(),
    };

    installFetchMock({
      messages: [
        { ok: true, body: seedMessages },
        { ok: true, body: [...seedMessages, secondUserMsg, assistantReply] },
      ],
      post: [
        { ok: false, body: {} },
        { ok: true, body: { userMessage: secondUserMsg, assistantMessage: assistantReply } },
      ],
    });

    renderWithClient(<ChatView />);

    await waitFor(() => expect(screen.getByText("Hello! How can I help?")).toBeInTheDocument());

    const textarea = screen.getByPlaceholderText(/Ask me/);

    await user.type(textarea, "first-msg");
    await user.keyboard("{Enter}");

    await waitFor(() => expect(screen.getByText("Not sent")).toBeInTheDocument());

    await user.type(textarea, "second-msg");
    await user.keyboard("{Enter}");

    await waitFor(() => expect(screen.getByText("Reply to second-msg.")).toBeInTheDocument());

    // The failed "first-msg" must still render before the later, successfully
    // sent "second-msg" — reflecting true chronological order — rather than
    // being appended after it just because it was resolved (as failed) later.
    const firstEl = screen.getByText("first-msg");
    const secondEl = screen.getByText("second-msg");
    expect(
      firstEl.compareDocumentPosition(secondEl) & Node.DOCUMENT_POSITION_FOLLOWING
    ).toBeTruthy();
    expect(screen.getByText("Not sent")).toBeInTheDocument();
  });

  it("does not render a duplicate bubble when two sends resolve concurrently", async () => {
    const user = userEvent.setup();
    const msgOne: ChatMessage = {
      id: "m2",
      role: "user",
      content: "msg one",
      timestamp: "2025-05-01T00:04:00.000Z",
    };
    const msgTwo: ChatMessage = {
      id: "m3",
      role: "user",
      content: "msg two",
      timestamp: "2025-05-01T00:04:05.000Z",
    };

    installFetchMock({
      messages: [
        { ok: true, body: seedMessages },
        { ok: true, body: [...seedMessages, msgOne, msgTwo] },
      ],
      post: { ok: true, body: {} },
      postDelayMs: 30,
    });

    renderWithClient(<ChatView />);

    await waitFor(() => expect(screen.getByText("Hello! How can I help?")).toBeInTheDocument());

    const textarea = screen.getByPlaceholderText(/Ask me/);

    await user.type(textarea, "msg one");
    await user.keyboard("{Enter}");
    await user.type(textarea, "msg two");
    await user.keyboard("{Enter}");

    await waitFor(() => {
      expect(screen.getAllByText("msg one")).toHaveLength(1);
      expect(screen.getAllByText("msg two")).toHaveLength(1);
    });
  });

  it("blocks sending while the initial message load is in an error state", async () => {
    const user = userEvent.setup();
    const fetchMock = installFetchMock({ messages: { ok: false, body: {} } });

    const { container } = renderWithClient(<ChatView />);

    await waitFor(() =>
      expect(screen.getByText("Couldn't load messages. Please try again.")).toBeInTheDocument()
    );

    const textarea = screen.getByPlaceholderText(/Ask me/);
    await user.type(textarea, "hi there");

    // The send button must be disabled while errored, not just while loading.
    const sendButton = container.querySelector("button[disabled]");
    expect(sendButton).toBeInTheDocument();

    await user.keyboard("{Enter}");

    // Blocked: no optimistic bubble, no POST, no typing indicator, and the
    // typed text is preserved rather than silently discarded. (The textarea
    // itself still contains "hi there" — queryAllByText also matches its
    // text node, so bubbles are asserted by excluding the textarea itself.)
    expect(textarea).toHaveValue("hi there");
    expect(
      screen.queryAllByText("hi there").filter((el) => el.tagName !== "TEXTAREA")
    ).toHaveLength(0);
    expect(document.querySelector(".animate-bounce")).not.toBeInTheDocument();
    expect(fetchMock.mock.calls.some((call) => call[1]?.method === "POST")).toBe(false);
    expect(toast.error).toHaveBeenCalledWith(
      "Couldn't load message history yet. Please wait for it to finish loading before sending.",
      { id: "chat-history-error" }
    );
  });

  it("does not produce a duplicate/stuck-pending bubble when the initial load fails, a send is attempted while errored, and the load later recovers with a body that already reflects that content", async () => {
    const user = userEvent.setup();
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });

    // Simulates a message that becomes visible on the server independently
    // of this client's own (blocked) send attempt — e.g. another device, or
    // a prior attempt from before the guard existed. What matters is that
    // the very first *successful* load, whenever it happens, is always
    // treated as pre-existing history exactly once.
    const persistedUserMsg: ChatMessage = {
      id: "m2",
      role: "user",
      content: "hi there",
      timestamp: "2025-05-01T00:04:00.000Z",
    };

    const fetchMock = installFetchMock({
      messages: [
        { ok: false, body: {} },
        { ok: true, body: [...seedMessages, persistedUserMsg] },
      ],
    });

    render(
      <QueryClientProvider client={queryClient}>
        <ChatView />
      </QueryClientProvider>
    );

    await waitFor(() =>
      expect(screen.getByText("Couldn't load messages. Please try again.")).toBeInTheDocument()
    );

    const textarea = screen.getByPlaceholderText(/Ask me/);
    await user.type(textarea, "hi there");
    await user.keyboard("{Enter}");

    // The attempted send while errored must be a true no-op: it never
    // creates an optimistic entry and never POSTs, so it can't be the thing
    // that later gets duplicated once the load recovers.
    expect(fetchMock.mock.calls.some((call) => call[1]?.method === "POST")).toBe(false);

    // Recover the query (standing in for React Query's built-in retry/
    // refetch, disabled here for determinism) with a body that already
    // contains "hi there" — the exact shape of the regression QA reported.
    await queryClient.refetchQueries({ queryKey: ["chat", "messages"] });

    await waitFor(() => expect(screen.getByText("hi there")).toBeInTheDocument());

    // Exactly one bubble, and no stuck "Sending…" indicator: the guard
    // prevented a second, un-reconcilable optimistic copy from ever being
    // created. (The blocked send never cleared the textarea, so it still
    // holds "hi there" too — excluded here since we're only counting
    // rendered message bubbles.)
    expect(
      screen.getAllByText("hi there").filter((el) => el.tagName !== "TEXTAREA")
    ).toHaveLength(1);
    expect(document.querySelector(".animate-bounce")).not.toBeInTheDocument();
    expect(fetchMock.mock.calls.some((call) => call[1]?.method === "POST")).toBe(false);
  });

  it("blocks sending and never fetches when the browser is offline at mount (paused fetchStatus, not isLoading/isError)", async () => {
    const user = userEvent.setup();
    // Under the default networkMode "online", a query created while offline
    // never attempts a fetch at all: fetchStatus is "paused", so
    // isPending=true/isFetching=false (isLoading=false) and status stays
    // "pending" (isError=false). Neither `isLoading` nor `isError` catches
    // this state, which is exactly why the guard must key off `!messages`.
    onlineManager.setOnline(false);
    const fetchMock = installFetchMock({ messages: { ok: true, body: seedMessages } });

    const { container } = renderWithClient(<ChatView />);

    const textarea = screen.getByPlaceholderText(/Ask me/);
    await user.type(textarea, "hi there");

    const sendButton = container.querySelector("button[disabled]");
    expect(sendButton).toBeInTheDocument();

    await user.keyboard("{Enter}");

    // Blocked: no optimistic bubble, no fetch attempted at all (not even the
    // GET, since the query never left the paused state), and the typed text
    // is preserved rather than silently discarded.
    expect(textarea).toHaveValue("hi there");
    expect(
      screen.queryAllByText("hi there").filter((el) => el.tagName !== "TEXTAREA")
    ).toHaveLength(0);
    expect(document.querySelector(".animate-bounce")).not.toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("keeps existing history visible and still allows sending after a later background refetch fails", async () => {
    const user = userEvent.setup();
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });

    const fetchMock = installFetchMock({
      // First GET (initial load) succeeds; a later, manually-triggered
      // background refetch (standing in for a poll/invalidate/refocus
      // refetch) fails.
      messages: [
        { ok: true, body: seedMessages },
        { ok: false, body: {} },
      ],
      post: { ok: true, body: {} },
    });

    render(
      <QueryClientProvider client={queryClient}>
        <ChatView />
      </QueryClientProvider>
    );

    await waitFor(() => expect(screen.getByText("Hello! How can I help?")).toBeInTheDocument());

    const toastCallsBeforeRefetch = vi.mocked(toast.error).mock.calls.length;

    await queryClient.refetchQueries({ queryKey: ["chat", "messages"] });

    await waitFor(() => {
      expect(queryClient.getQueryState(["chat", "messages"])?.status).toBe("error");
    });

    // The already-loaded conversation must remain visible — not replaced by
    // the hard error screen — since `messages` (React Query's last
    // successful `data`) is still populated despite the latest fetch
    // erroring.
    expect(screen.getByText("Hello! How can I help?")).toBeInTheDocument();
    expect(
      screen.queryByText("Couldn't load messages. Please try again.")
    ).not.toBeInTheDocument();

    // Sending must still be allowed: the reconciliation baseline was already
    // captured on the first successful load, so a later transient error must
    // not re-block it.
    const textarea = screen.getByPlaceholderText(/Ask me/);
    await user.type(textarea, "still works");
    await user.keyboard("{Enter}");

    expect(textarea).toHaveValue("");
    await waitFor(() => {
      expect(fetchMock.mock.calls.some((call) => call[1]?.method === "POST")).toBe(true);
    });
    // No new "couldn't load history" toast was raised by this send.
    expect(vi.mocked(toast.error).mock.calls.length).toBe(toastCallsBeforeRefetch);
  });
});
