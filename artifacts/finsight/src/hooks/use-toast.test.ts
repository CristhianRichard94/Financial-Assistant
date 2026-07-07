import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import type { ReactNode } from "react";
import { reducer } from "@/hooks/use-toast";
import type { ToastProps } from "@/components/ui/toast";

type ToasterToast = ToastProps & {
  id: string;
  title?: ReactNode;
  description?: ReactNode;
};

function makeToast(id: string, overrides: Partial<ToasterToast> = {}): ToasterToast {
  return { id, open: true, ...overrides };
}

describe("use-toast reducer", () => {
  // DISMISS_TOAST has a side effect: it schedules a real `setTimeout` (via
  // `addToRemoveQueue`) to eventually dispatch REMOVE_TOAST. Fake timers keep
  // that from leaving a dangling ~1,000,000ms real timer running after the
  // test finishes.
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("ADD_TOAST adds a toast to an empty state", () => {
    const state = { toasts: [] };
    const toast = makeToast("1");

    const next = reducer(state, { type: "ADD_TOAST", toast });

    expect(next.toasts).toEqual([toast]);
  });

  it("ADD_TOAST truncates to TOAST_LIMIT (1), keeping only the newest toast", () => {
    const state = { toasts: [makeToast("1")] };
    const toast2 = makeToast("2");

    const next = reducer(state, { type: "ADD_TOAST", toast: toast2 });

    expect(next.toasts).toHaveLength(1);
    expect(next.toasts[0].id).toBe("2");
  });

  it("UPDATE_TOAST merges fields into the matching toast", () => {
    const state = { toasts: [makeToast("1", { title: "Original" })] };

    const next = reducer(state, {
      type: "UPDATE_TOAST",
      toast: { id: "1", title: "Updated" },
    });

    expect(next.toasts[0].title).toBe("Updated");
    expect(next.toasts[0].id).toBe("1");
  });

  it("UPDATE_TOAST leaves non-matching toasts unchanged", () => {
    const state = { toasts: [makeToast("1", { title: "Keep me" })] };

    const next = reducer(state, {
      type: "UPDATE_TOAST",
      toast: { id: "does-not-exist", title: "Should not apply" },
    });

    expect(next.toasts[0].title).toBe("Keep me");
  });

  it("DISMISS_TOAST with a toastId sets only that toast's open to false", () => {
    const state = { toasts: [makeToast("1"), makeToast("2")] };

    const next = reducer(state, { type: "DISMISS_TOAST", toastId: "1" });

    expect(next.toasts.find((t) => t.id === "1")?.open).toBe(false);
    expect(next.toasts.find((t) => t.id === "2")?.open).toBe(true);
  });

  it("DISMISS_TOAST without a toastId sets all toasts' open to false", () => {
    const state = { toasts: [makeToast("1"), makeToast("2")] };

    const next = reducer(state, { type: "DISMISS_TOAST", toastId: undefined });

    expect(next.toasts.every((t) => t.open === false)).toBe(true);
  });

  it("REMOVE_TOAST with a toastId removes only that toast", () => {
    const state = { toasts: [makeToast("1"), makeToast("2")] };

    const next = reducer(state, { type: "REMOVE_TOAST", toastId: "1" });

    expect(next.toasts).toHaveLength(1);
    expect(next.toasts[0].id).toBe("2");
  });

  it("REMOVE_TOAST without a toastId clears all toasts", () => {
    const state = { toasts: [makeToast("1"), makeToast("2")] };

    const next = reducer(state, { type: "REMOVE_TOAST", toastId: undefined });

    expect(next.toasts).toEqual([]);
  });
});
