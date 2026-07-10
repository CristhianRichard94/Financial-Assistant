import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { LoginForm } from "@/app/login/LoginForm";

const signInWithOAuth = vi.fn().mockResolvedValue({ data: {}, error: null });

vi.mock("@/lib/supabase/browser", () => ({
  createClient: () => ({
    auth: {
      signInWithOAuth: (...args: unknown[]) => signInWithOAuth(...args),
    },
  }),
}));

describe("LoginForm", () => {
  afterEach(() => {
    vi.clearAllMocks();
  });

  it("renders the heading, brand lockup, and idle sign-in button with no alert", () => {
    render(<LoginForm />);

    expect(screen.getByRole("heading", { name: "Sign in to FinSight" })).toBeInTheDocument();
    expect(screen.getByText("FinSight")).toBeInTheDocument();
    expect(screen.getByText("AI-powered finance assistant")).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();

    const button = screen.getByRole("button", { name: /sign in with google/i });
    expect(button).not.toBeDisabled();
    expect(button).toHaveAttribute("aria-busy", "false");
  });

  it("renders the cancelled alert copy", () => {
    render(<LoginForm error="cancelled" />);

    expect(screen.getByRole("alert")).toHaveTextContent("Sign-in was cancelled");
    expect(screen.getByRole("alert")).toHaveTextContent(
      "You can try again whenever you're ready."
    );
  });

  it("renders the failed alert copy", () => {
    render(<LoginForm error="failed" />);

    expect(screen.getByRole("alert")).toHaveTextContent("Something went wrong");
    expect(screen.getByRole("alert")).toHaveTextContent(
      "We couldn't sign you in. Please try again."
    );
  });

  it("shows a spinner and disables the button, and calls signInWithOAuth, on click", async () => {
    const user = userEvent.setup();
    render(<LoginForm />);

    const button = screen.getByRole("button", { name: /sign in with google/i });
    await user.click(button);

    expect(button).toBeDisabled();
    expect(button).toHaveAttribute("aria-busy", "true");
    expect(screen.getByText("Redirecting…")).toBeInTheDocument();
    expect(signInWithOAuth).toHaveBeenCalledWith({
      provider: "google",
      options: { redirectTo: expect.stringContaining("/auth/callback") },
    });
  });

  it("forwards a safe redirectTo as a query param on the callback URL", async () => {
    const user = userEvent.setup();
    render(<LoginForm redirectTo="/chat" />);

    await user.click(screen.getByRole("button", { name: /sign in with google/i }));

    const [[call]] = signInWithOAuth.mock.calls;
    expect(call.options.redirectTo).toContain("redirect=%2Fchat");
  });

  it("drops an unsafe redirectTo instead of forwarding it", async () => {
    const user = userEvent.setup();
    render(<LoginForm redirectTo="https://evil.com" />);

    await user.click(screen.getByRole("button", { name: /sign in with google/i }));

    const [[call]] = signInWithOAuth.mock.calls;
    expect(call.options.redirectTo).not.toContain("evil.com");
    expect(call.options.redirectTo).not.toContain("redirect=");
  });

  it("re-enables the button and shows the failed alert when signInWithOAuth resolves with an error", async () => {
    signInWithOAuth.mockResolvedValueOnce({
      data: {},
      error: new Error("provider not configured"),
    });
    const consoleErrorSpy = vi.spyOn(console, "error").mockImplementation(() => {});
    const user = userEvent.setup();
    render(<LoginForm />);

    const button = screen.getByRole("button", { name: /sign in with google/i });
    await user.click(button);

    expect(button).not.toBeDisabled();
    expect(button).toHaveAttribute("aria-busy", "false");
    expect(screen.queryByText("Redirecting…")).not.toBeInTheDocument();
    expect(screen.getByRole("alert")).toHaveTextContent("Something went wrong");

    consoleErrorSpy.mockRestore();
  });

  it("re-enables the button and shows the failed alert when signInWithOAuth throws", async () => {
    signInWithOAuth.mockRejectedValueOnce(new Error("network error"));
    const consoleErrorSpy = vi.spyOn(console, "error").mockImplementation(() => {});
    const user = userEvent.setup();
    render(<LoginForm />);

    const button = screen.getByRole("button", { name: /sign in with google/i });
    await user.click(button);

    expect(button).not.toBeDisabled();
    expect(button).toHaveAttribute("aria-busy", "false");
    expect(screen.getByRole("alert")).toHaveTextContent("Something went wrong");

    consoleErrorSpy.mockRestore();
  });

  it("lets the user retry after a failed sign-in attempt", async () => {
    signInWithOAuth.mockRejectedValueOnce(new Error("network error"));
    const consoleErrorSpy = vi.spyOn(console, "error").mockImplementation(() => {});
    const user = userEvent.setup();
    render(<LoginForm />);

    const button = screen.getByRole("button", { name: /sign in with google/i });
    await user.click(button);
    expect(screen.getByRole("alert")).toBeInTheDocument();

    signInWithOAuth.mockResolvedValueOnce({ data: {}, error: null });
    await user.click(screen.getByRole("button", { name: /sign in with google/i }));

    expect(signInWithOAuth).toHaveBeenCalledTimes(2);
    expect(screen.getByText("Redirecting…")).toBeInTheDocument();

    consoleErrorSpy.mockRestore();
  });
});
