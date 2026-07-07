import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { DocumentsView } from "@/components/views/DocumentsView";
import type { Document } from "@/lib/store";

// NOTE: Full drag-and-drop file upload simulation through react-dropzone is
// intentionally out of scope here - simulating native DataTransfer/drop
// events reliably in jsdom is disproportionately complex relative to the
// value it adds, given the upload flow's core logic (size validation,
// POST call, toast on success/failure) is already covered indirectly via
// the delete-flow and route-handler tests. The drop zone's static states
// (idle/drag-active/uploading) are visual only and not asserted here.

vi.mock("sonner", () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
  },
}));

import { toast } from "sonner";

const docs: Document[] = [
  {
    id: "1",
    name: "bank_statement.pdf",
    type: "pdf",
    size: 248320,
    status: "processed",
    uploadedAt: "2025-05-01T00:00:00.000Z",
  },
];

function renderWithClient(ui: React.ReactElement) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(<QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>);
}

function installFetchMock(options: {
  documents: { ok: boolean; body: unknown };
  deleteOk?: boolean;
}) {
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = typeof input === "string" ? input : input.toString();

    if (init?.method === "DELETE") {
      const ok = options.deleteOk ?? true;
      return { ok, status: ok ? 200 : 500, json: async () => ({}) } as Response;
    }
    if (url.includes("/api/documents")) {
      const { ok, body } = options.documents;
      return { ok, status: ok ? 200 : 500, json: async () => body } as Response;
    }
    return { ok: false, status: 404, json: async () => ({}) } as Response;
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

describe("DocumentsView", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.clearAllMocks();
  });

  it("shows loading skeletons while documents are loading", () => {
    vi.stubGlobal("fetch", vi.fn(() => new Promise(() => {})));

    const { container } = renderWithClient(<DocumentsView />);

    expect(container.querySelectorAll(".animate-pulse").length).toBeGreaterThan(0);
  });

  it("shows an error state when documents fail to load", async () => {
    installFetchMock({ documents: { ok: false, body: {} } });

    renderWithClient(<DocumentsView />);

    await waitFor(() =>
      expect(
        screen.getByText("Couldn't load your documents. Please try again.")
      ).toBeInTheDocument()
    );
  });

  it("shows the empty state when there are no documents", async () => {
    installFetchMock({ documents: { ok: true, body: [] } });

    renderWithClient(<DocumentsView />);

    await waitFor(() =>
      expect(
        screen.getByText("No documents yet. Upload one above to get started.")
      ).toBeInTheDocument()
    );
  });

  it("renders the populated documents table", async () => {
    installFetchMock({ documents: { ok: true, body: docs } });

    renderWithClient(<DocumentsView />);

    await waitFor(() => expect(screen.getByText("bank_statement.pdf")).toBeInTheDocument());
    expect(screen.getByText("242.5 KB")).toBeInTheDocument();
    expect(screen.getByText("Processed")).toBeInTheDocument();
  });

  it("deletes a document and shows a success toast", async () => {
    const user = userEvent.setup();
    installFetchMock({ documents: { ok: true, body: docs } });

    renderWithClient(<DocumentsView />);

    await waitFor(() => expect(screen.getByText("bank_statement.pdf")).toBeInTheDocument());

    const deleteButton = screen.getByLabelText("Delete document");
    await user.click(deleteButton);

    await waitFor(() => expect(toast.success).toHaveBeenCalledWith("Document deleted"));
  });

  it("shows an error toast when deletion fails", async () => {
    const user = userEvent.setup();
    installFetchMock({ documents: { ok: true, body: docs }, deleteOk: false });

    renderWithClient(<DocumentsView />);

    await waitFor(() => expect(screen.getByText("bank_statement.pdf")).toBeInTheDocument());

    const deleteButton = screen.getByLabelText("Delete document");
    await user.click(deleteButton);

    await waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith("Failed to delete document")
    );
  });
});
