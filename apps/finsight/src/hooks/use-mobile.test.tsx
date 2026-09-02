import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { useIsMobile } from "@/hooks/use-mobile";

type Listener = (event: MediaQueryListEvent) => void;

function setInnerWidth(width: number) {
  Object.defineProperty(window, "innerWidth", {
    writable: true,
    configurable: true,
    value: width,
  });
}

function installMatchMediaMock() {
  const listeners: Listener[] = [];
  const mql: Partial<MediaQueryList> & { _fireChange: () => void } = {
    matches: false,
    media: "",
    addEventListener: (_event: string, listener: EventListenerOrEventListenerObject) => {
      listeners.push(listener as Listener);
    },
    removeEventListener: (_event: string, listener: EventListenerOrEventListenerObject) => {
      const idx = listeners.indexOf(listener as Listener);
      if (idx > -1) listeners.splice(idx, 1);
    },
    _fireChange: () => {
      listeners.forEach((listener) => listener({} as MediaQueryListEvent));
    },
  };

  const matchMediaMock = vi.fn().mockReturnValue(mql);
  vi.stubGlobal("matchMedia", matchMediaMock);
  window.matchMedia = matchMediaMock as unknown as typeof window.matchMedia;

  return { mql, matchMediaMock };
}

describe("useIsMobile", () => {
  let restoreWidth: number;

  beforeEach(() => {
    restoreWidth = window.innerWidth;
  });

  afterEach(() => {
    setInnerWidth(restoreWidth);
    vi.unstubAllGlobals();
  });

  it("returns true when the window is narrower than the mobile breakpoint", () => {
    setInnerWidth(500);
    installMatchMediaMock();

    const { result } = renderHook(() => useIsMobile());

    expect(result.current).toBe(true);
  });

  it("returns false when the window is at or above the mobile breakpoint", () => {
    setInnerWidth(1024);
    installMatchMediaMock();

    const { result } = renderHook(() => useIsMobile());

    expect(result.current).toBe(false);
  });

  it("updates when a matchMedia 'change' event fires after a resize", () => {
    setInnerWidth(1024);
    const { mql } = installMatchMediaMock();

    const { result } = renderHook(() => useIsMobile());
    expect(result.current).toBe(false);

    setInnerWidth(400);
    act(() => {
      mql._fireChange();
    });

    expect(result.current).toBe(true);
  });

  it("removes the change listener on unmount", () => {
    setInnerWidth(1024);
    const { mql } = installMatchMediaMock();
    const removeSpy = vi.spyOn(mql, "removeEventListener" as never);

    const { unmount } = renderHook(() => useIsMobile());
    unmount();

    expect(removeSpy).toHaveBeenCalledWith("change", expect.any(Function));
  });
});
