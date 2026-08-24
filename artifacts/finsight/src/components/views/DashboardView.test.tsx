import { describe, it, expect, vi, afterEach } from "vitest";
import { renderWithIntl as render, screen, waitFor } from "@/test/renderWithIntl";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { DashboardView } from "@/components/views/DashboardView";
import type { DashboardSummary, Transaction } from "@/lib/types";

const happySummary: DashboardSummary = {
  totalIncome: 8450,
  totalSpending: 5520,
  netSavings: 2930,
  incomeTrend: 3.2,
  spendingTrend: -1.8,
  savingsTrend: 12.4,
  documentCount: 2,
  totalDocumentCount: 2,
  transactionCount: 7,
  categoryBreakdown: [{ category: "Housing", amount: 2100, percentage: 38 }],
};

const activity: Transaction[] = [
  {
    id: "1",
    description: "Whole Foods Market",
    category: "Groceries",
    amount: -87.43,
    date: "2025-05-01T00:00:00.000Z",
  },
];

function renderWithClient(ui: React.ReactElement) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(<QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>);
}

function mockFetchSequence(responses: Array<{ url: string; body?: unknown; ok?: boolean; status?: number }>) {
  const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
    const url = typeof input === "string" ? input : input.toString();
    const match = responses.find((r) => url.includes(r.url));
    if (!match) {
      return { ok: false, status: 404, json: async () => ({}) } as Response;
    }
    return {
      ok: match.ok ?? true,
      status: match.status ?? 200,
      json: async () => match.body,
    } as Response;
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

describe("DashboardView", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("shows loading skeletons before data resolves", async () => {
    vi.stubGlobal("fetch", vi.fn(() => new Promise(() => {})));

    const { container } = renderWithClient(<DashboardView />);

    expect(container.querySelectorAll(".animate-pulse").length).toBeGreaterThan(0);
    expect(screen.queryByText("Total Income")).not.toBeInTheDocument();
  });

  it("renders populated stat cards with correctly formatted values (happy path)", async () => {
    mockFetchSequence([
      { url: "/api/dashboard/summary", body: happySummary },
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

  it("shows the zero-docs empty state when the user has no documents at all", async () => {
    mockFetchSequence([
      {
        url: "/api/dashboard/summary",
        body: {
          totalIncome: 0,
          totalSpending: 0,
          netSavings: 0,
          incomeTrend: 0,
          spendingTrend: 0,
          savingsTrend: 0,
          documentCount: 0,
          totalDocumentCount: 0,
          transactionCount: 0,
          categoryBreakdown: [],
        },
      },
      { url: "/api/dashboard/activity", body: [] },
    ]);

    renderWithClient(<DashboardView />);

    await waitFor(() => expect(screen.getByText("No financial data yet")).toBeInTheDocument());
    expect(
      screen.getByText("Upload a bank statement or CSV to see your overview.")
    ).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Upload documents" })).toHaveAttribute(
      "href",
      "/documents"
    );
    expect(screen.queryByText("Total Income")).not.toBeInTheDocument();
  });

  it("shows the processing notice when documents exist but none have completed yet", async () => {
    mockFetchSequence([
      {
        url: "/api/dashboard/summary",
        body: {
          totalIncome: 0,
          totalSpending: 0,
          netSavings: 0,
          incomeTrend: 0,
          spendingTrend: 0,
          savingsTrend: 0,
          documentCount: 0,
          totalDocumentCount: 1,
          transactionCount: 0,
          categoryBreakdown: [],
        },
      },
      { url: "/api/dashboard/activity", body: [] },
    ]);

    renderWithClient(<DashboardView />);

    await waitFor(() =>
      expect(
        screen.getByText(
          "Your documents are still processing. This page will update automatically."
        )
      ).toBeInTheDocument()
    );
    expect(screen.getByRole("link", { name: "View documents" })).toHaveAttribute(
      "href",
      "/documents"
    );
    expect(screen.queryByText("Total Income")).not.toBeInTheDocument();
  });

  it("shows $0 stat cards with no trend badge and the amber banner when there are zero transactions", async () => {
    mockFetchSequence([
      {
        url: "/api/dashboard/summary",
        body: {
          totalIncome: 0,
          totalSpending: 0,
          netSavings: 0,
          incomeTrend: 0,
          spendingTrend: 0,
          savingsTrend: 0,
          documentCount: 1,
          totalDocumentCount: 1,
          transactionCount: 0,
          categoryBreakdown: [],
        },
      },
      { url: "/api/dashboard/activity", body: [] },
    ]);

    renderWithClient(<DashboardView />);

    await waitFor(() => expect(screen.getByText("Total Income")).toBeInTheDocument());
    expect(screen.getAllByText("$0")).toHaveLength(3);
    expect(screen.queryByText(/vs last month/)).not.toBeInTheDocument();
    expect(
      screen.getByText(/We couldn't find any transactions in your uploaded documents/)
    ).toBeInTheDocument();
    expect(screen.getByText("No transactions found yet.")).toBeInTheDocument();
    expect(screen.getByText("No spending data to show yet.")).toBeInTheDocument();
  });

  it("shows a retry error for the summary-driven regions when the summary request fails, independent of activity", async () => {
    mockFetchSequence([
      { url: "/api/dashboard/summary", ok: false, status: 500, body: {} },
      { url: "/api/dashboard/activity", body: activity },
    ]);

    renderWithClient(<DashboardView />);

    await waitFor(() =>
      expect(
        screen.getByText("Couldn't load your dashboard summary. Please try again.")
      ).toBeInTheDocument()
    );
    const alerts = screen.getAllByRole("alert");
    expect(alerts.length).toBeGreaterThan(0);
    expect(screen.getAllByText("Try again").length).toBeGreaterThan(0);

    // Activity loaded fine independently, so its region should still render.
    await waitFor(() => expect(screen.getByText("Whole Foods Market")).toBeInTheDocument());
  });

  it("shows a retry error only for the activity region when just the activity request fails", async () => {
    mockFetchSequence([
      { url: "/api/dashboard/summary", body: happySummary },
      { url: "/api/dashboard/activity", ok: false, status: 500, body: {} },
    ]);

    renderWithClient(<DashboardView />);

    await waitFor(() => expect(screen.getByText("Total Income")).toBeInTheDocument());
    await waitFor(() =>
      expect(
        screen.getByText("Couldn't load recent activity. Please try again.")
      ).toBeInTheDocument()
    );
    expect(screen.getByText("$8,450")).toBeInTheDocument();
  });
});
