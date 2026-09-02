import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen } from "@testing-library/react";
import ProtectedLayout from "@/app/(protected)/layout";

vi.mock("@/lib/supabase/server", () => ({
  createClient: vi.fn(),
}));

// Mirrors `next/navigation`'s real `redirect()`, which throws to unwind
// rendering rather than returning normally - without this, code after the
// `redirect("/login")` call in the layout (which reads properties off the
// null `user`) would run and throw an unrelated TypeError instead.
vi.mock("next/navigation", () => ({
  redirect: vi.fn((url: string) => {
    throw new Error(`NEXT_REDIRECT:${url}`);
  }),
}));

vi.mock("@/components/AppLayout", () => ({
  AppLayout: ({
    user,
    children,
  }: {
    user: { email: string; displayName: string | null; avatarUrl: string | null };
    children: React.ReactNode;
  }) => (
    <div
      data-testid="app-layout"
      data-email={user.email}
      data-display-name={user.displayName === null ? "null" : user.displayName}
      data-avatar-url={user.avatarUrl === null ? "null" : user.avatarUrl}
    >
      {children}
    </div>
  ),
}));

import { createClient } from "@/lib/supabase/server";
import { redirect } from "next/navigation";

function makeSupabaseClient(user: unknown) {
  return {
    auth: {
      getUser: vi.fn().mockResolvedValue({ data: { user } }),
    },
  };
}

describe("(protected) layout", () => {
  afterEach(() => {
    vi.clearAllMocks();
  });

  it("redirects to /login when there is no session", async () => {
    vi.mocked(createClient).mockResolvedValue(makeSupabaseClient(null) as never);

    await expect(
      ProtectedLayout({ children: <div>content</div> })
    ).rejects.toThrow("NEXT_REDIRECT:/login");
    expect(redirect).toHaveBeenCalledWith("/login");
  });

  it("renders AppLayout with the mapped user and children when signed in", async () => {
    vi.mocked(createClient).mockResolvedValue(
      makeSupabaseClient({
        email: "jane@example.com",
        user_metadata: { full_name: "Jane Doe", avatar_url: "https://example.com/a.png" },
      }) as never
    );

    const element = await ProtectedLayout({ children: <div>protected content</div> });
    render(element);

    const appLayout = screen.getByTestId("app-layout");
    expect(appLayout).toHaveAttribute("data-email", "jane@example.com");
    expect(appLayout).toHaveAttribute("data-display-name", "Jane Doe");
    expect(appLayout).toHaveAttribute("data-avatar-url", "https://example.com/a.png");
    expect(screen.getByText("protected content")).toBeInTheDocument();
    expect(redirect).not.toHaveBeenCalled();
  });

  it("falls back to an empty email and null displayName/avatarUrl when absent from user_metadata", async () => {
    vi.mocked(createClient).mockResolvedValue(
      makeSupabaseClient({ email: undefined, user_metadata: {} }) as never
    );

    const element = await ProtectedLayout({ children: <div>x</div> });
    render(element);

    const appLayout = screen.getByTestId("app-layout");
    expect(appLayout).toHaveAttribute("data-email", "");
    expect(appLayout).toHaveAttribute("data-display-name", "null");
    expect(appLayout).toHaveAttribute("data-avatar-url", "null");
  });
});
