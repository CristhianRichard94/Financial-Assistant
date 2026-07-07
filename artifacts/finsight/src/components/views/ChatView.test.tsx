import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ChatView } from "@/components/views/ChatView";
import type { ChatMessage, Document } from "@/lib/store";

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
  post?: RouteConfig;
  postDelayMs?: number;
}) {
  let messageCallCount = 0;
  const messagesQueue = Array.isArray(routes.messages) ? routes.messages : [routes.messages];

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
      const route = routes.post ?? { ok: true, body: {} };
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
});
