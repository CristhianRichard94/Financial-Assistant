import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { DashboardView } from "@/components/views/DashboardView";
import type { DashboardSummary, Transaction } from "@/lib/store";

const summary: DashboardSummary = {
  totalIncome: 8450,
  totalSpending: 5520,
  netSavings: 2930,
  incomeTrend: 3.2,
  spendingTrend: -1.8,
  savingsTrend: 12.4,
  documentCount: 2,
  categoryBreakdown: [
    { category: "Housing", amount: 2100, percentage: 38, color: "#6366f1" },
  ],
};

const activity: Transaction[] = [
  {
    id: "1",
    description: "Whole Foods Market",
    category: "Groceries",
    amount: -87.43,
    date: "2025-05-01T00:00:00.000Z",
    icon: "🛒",
  },
];

function renderWithClient(ui: React.ReactElement) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(<QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>);
}

function mockFetchSequence(responses: Array<{ url: string; body: unknown }>) {
  const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
    const url = typeof input === "string" ? input : input.toString();
    const match = responses.find((r) => url.includes(r.url));
    if (!match) {
      return { ok: false, status: 404, json: async () => ({}) } as Response;
    }
    return { ok: true, status: 200, json: async () => match.body } as Response;
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

describe("DashboardView", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("shows loading skeletons before data resolves", async () => {
    // Never-resolving fetch keeps the view in a loading state.
    vi.stubGlobal("fetch", vi.fn(() => new Promise(() => {})));

    const { container } = renderWithClient(<DashboardView />);

    expect(container.querySelectorAll(".animate-pulse").length).toBeGreaterThan(0);
    expect(screen.queryByText("Total Income")).not.toBeInTheDocument();
  });

  it("renders populated stat cards with correctly formatted values", async () => {
    mockFetchSequence([
      { url: "/api/dashboard/summary", body: summary },
      { url: "/api/dashboard/activity", body: activity },
    ]);

    renderWithClient(<DashboardView />);

    await waitFor(() => expect(screen.getByText("Total Income")).toBeInTheDocument());

    expect(screen.getByText("$8,450")).toBeInTheDocument();
    expect(screen.getByText("$5,520")).toBeInTheDocument();
    expect(screen.getByText("$2,930")).toBeInTheDocument();
    expect(screen.getByText("+3.2% vs last month")).toBeInTheDocument();
    expect(screen.getByText("-1.8% vs last month")).toBeInTheDocument();
    expect(screen.getByText("Analyzed from 2 documents")).toBeInTheDocument();

    await waitFor(() => expect(screen.getByText("Whole Foods Market")).toBeInTheDocument());
    expect(screen.getByText("-$87")).toBeInTheDocument();
    expect(screen.getByText("Housing")).toBeInTheDocument();
  });
});
