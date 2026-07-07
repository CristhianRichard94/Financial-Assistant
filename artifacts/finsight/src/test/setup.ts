import "@testing-library/jest-dom/vitest";
import { afterEach } from "vitest";
import { cleanup } from "@testing-library/react";

// `@testing-library/react`'s automatic per-test cleanup relies on a *global*
// `afterEach` being present (it feature-detects `typeof afterEach ===
// "function"`). Since this project intentionally does not enable Vitest's
// `globals: true` option, that auto-registration never fires, so without
// this explicit call, DOM trees rendered by one test would leak into the
// next test in the same file. Register it explicitly here instead.
afterEach(() => {
  cleanup();
});

// Pin the timezone so date-formatting assertions (e.g. `formatDate` in
// `src/lib/utils.ts`) are deterministic regardless of the host machine's
// local timezone.
process.env.TZ = "UTC";

// jsdom does not implement `window.matchMedia`. Several parts of the app
// (e.g. `src/hooks/use-mobile.tsx`) rely on it, so provide a lightweight
// mock. Individual tests can override `window.matchMedia` further if they
// need to control the returned `MediaQueryList` (e.g. to simulate a
// `change` event).
if (typeof window !== "undefined" && !window.matchMedia) {
  Object.defineProperty(window, "matchMedia", {
    writable: true,
    configurable: true,
    value: (query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: () => {},
      removeListener: () => {},
      addEventListener: () => {},
      removeEventListener: () => {},
      dispatchEvent: () => false,
    }),
  });
}

// jsdom does not implement `Element.prototype.scrollIntoView` either (used
// by `src/components/views/ChatView.tsx` to auto-scroll to the latest
// message), so stub it out as a no-op to avoid a TypeError during render.
if (typeof window !== "undefined" && !window.HTMLElement.prototype.scrollIntoView) {
  window.HTMLElement.prototype.scrollIntoView = () => {};
}
