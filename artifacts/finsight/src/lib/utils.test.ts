import { describe, it, expect } from "vitest";
import { cn, formatCurrency, formatDate, formatFileSize } from "@/lib/utils";

describe("cn", () => {
  it("merges class names, dropping falsy values", () => {
    expect(cn("a", false && "b", "c")).toBe("a c");
  });

  it("merges conflicting tailwind classes, keeping the last one", () => {
    expect(cn("p-2", "p-4")).toBe("p-4");
  });
});

describe("formatCurrency", () => {
  it("formats a positive amount as USD with no decimals", () => {
    expect(formatCurrency(8450)).toBe("$8,450");
  });

  it("formats a negative amount", () => {
    expect(formatCurrency(-87.43)).toBe("-$87");
  });

  it("formats zero", () => {
    expect(formatCurrency(0)).toBe("$0");
  });
});

describe("formatDate", () => {
  it("formats an ISO date string", () => {
    expect(formatDate("2025-05-01T00:00:00.000Z")).toBe("May 1, 2025");
  });

  it("formats a Date instance", () => {
    expect(formatDate(new Date("2025-01-15T12:00:00.000Z"))).toBe("Jan 15, 2025");
  });
});

describe("formatFileSize", () => {
  it("formats 0 bytes", () => {
    expect(formatFileSize(0)).toBe("0 B");
  });

  it("formats bytes under 1024 as B", () => {
    expect(formatFileSize(1023)).toBe("1023 B");
  });

  it("formats exactly 1024 bytes as KB", () => {
    expect(formatFileSize(1024)).toBe("1.0 KB");
  });

  it("formats bytes just under 1MB as KB", () => {
    expect(formatFileSize(1024 * 1024 - 1)).toBe("1024.0 KB");
  });

  it("formats exactly 1MB as MB", () => {
    expect(formatFileSize(1024 * 1024)).toBe("1.0 MB");
  });

  it("formats a large size as MB", () => {
    expect(formatFileSize(1240000)).toBe("1.2 MB");
  });

  it("formats a negative amount as B (falls through to the < 1024 branch)", () => {
    expect(formatFileSize(-10)).toBe("-10 B");
  });
});
