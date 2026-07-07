import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { AppLayout } from "@/components/AppLayout";

const mockUsePathname = vi.fn();

vi.mock("next/navigation", () => ({
  usePathname: () => mockUsePathname(),
}));

describe("AppLayout", () => {
  afterEach(() => {
    vi.clearAllMocks();
  });

  it("highlights the Dashboard nav link when on /dashboard", () => {
    mockUsePathname.mockReturnValue("/dashboard");

    render(
      <AppLayout>
        <div>content</div>
      </AppLayout>
    );

    const dashboardLinks = screen.getAllByRole("link", { name: "Dashboard" });
    const documentsLinks = screen.getAllByRole("link", { name: "Documents" });

    // Desktop sidebar is always rendered; take the first (desktop) instance.
    expect(dashboardLinks[0].className).toContain("bg-[hsl(var(--primary))]");
    expect(documentsLinks[0].className).not.toContain("bg-[hsl(var(--primary))]");
  });

  it("highlights the Documents nav link (including nested routes) when on /documents/123", () => {
    mockUsePathname.mockReturnValue("/documents/123");

    render(
      <AppLayout>
        <div>content</div>
      </AppLayout>
    );

    const documentsLinks = screen.getAllByRole("link", { name: "Documents" });
    const chatLinks = screen.getAllByRole("link", { name: "Chat" });

    expect(documentsLinks[0].className).toContain("bg-[hsl(var(--primary))]");
    expect(chatLinks[0].className).not.toContain("bg-[hsl(var(--primary))]");
  });

  it("renders the page content", () => {
    mockUsePathname.mockReturnValue("/dashboard");

    render(
      <AppLayout>
        <div>page content</div>
      </AppLayout>
    );

    expect(screen.getByText("page content")).toBeInTheDocument();
  });

  it("opens and closes the mobile nav overlay via button clicks", async () => {
    const user = userEvent.setup();
    mockUsePathname.mockReturnValue("/dashboard");

    const { container } = render(
      <AppLayout>
        <div>content</div>
      </AppLayout>
    );

    // Overlay is not rendered until opened.
    expect(container.querySelector(".fixed.inset-0")).not.toBeInTheDocument();

    const openButton = screen.getAllByRole("button")[0];
    await user.click(openButton);

    expect(container.querySelector(".fixed.inset-0")).toBeInTheDocument();

    // The mobile sidebar's close (X) button is the second button rendered
    // once the overlay is open (first is the header's hamburger button).
    const closeButton = screen.getAllByRole("button").find((btn) =>
      btn.querySelector("svg.lucide-x")
    );
    expect(closeButton).toBeDefined();
    await user.click(closeButton!);

    expect(container.querySelector(".fixed.inset-0")).not.toBeInTheDocument();
  });
});
