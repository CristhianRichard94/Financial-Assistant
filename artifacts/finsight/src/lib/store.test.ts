import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import type { store as StoreType } from "@/lib/store";

// `store.ts` holds module-level mutable singleton arrays with no reset
// export, so every test gets a fresh module instance via `vi.resetModules()`
// + a dynamic import, to avoid state leaking between tests.
async function freshStore(): Promise<typeof StoreType> {
  vi.resetModules();
  const mod = await import("@/lib/store");
  return mod.store;
}

describe("store.documents", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("lists the seeded documents", async () => {
    const store = await freshStore();
    const docs = store.documents.list();
    expect(docs).toHaveLength(3);
  });

  it("list() returns a copy, not the live array", async () => {
    const store = await freshStore();
    const docs = store.documents.list();
    docs.push({
      id: "fake",
      name: "fake.pdf",
      type: "pdf",
      size: 1,
      status: "pending",
      uploadedAt: new Date().toISOString(),
    });
    expect(store.documents.list()).toHaveLength(3);
  });

  it("add() creates a pending document that transitions to processing then processed", async () => {
    const store = await freshStore();
    const doc = store.documents.add("statement.pdf", 12345);

    expect(doc.status).toBe("pending");
    expect(doc.name).toBe("statement.pdf");
    expect(doc.type).toBe("pdf");
    expect(doc.size).toBe(12345);

    let docs = store.documents.list();
    expect(docs.find((d) => d.id === doc.id)?.status).toBe("pending");

    await vi.advanceTimersByTimeAsync(1000);
    docs = store.documents.list();
    expect(docs.find((d) => d.id === doc.id)?.status).toBe("processing");

    await vi.advanceTimersByTimeAsync(3000);
    docs = store.documents.list();
    expect(docs.find((d) => d.id === doc.id)?.status).toBe("processed");
  });

  it("infers document type from the filename extension", async () => {
    const store = await freshStore();
    expect(store.documents.add("data.csv", 1).type).toBe("csv");
    expect(store.documents.add("receipt.jpg", 1).type).toBe("image");
    expect(store.documents.add("no-extension", 1).type).toBe("image");
  });

  it("delete() removes an existing document and returns true", async () => {
    const store = await freshStore();
    const [first] = store.documents.list();
    const result = store.documents.delete(first.id);

    expect(result).toBe(true);
    expect(store.documents.list().find((d) => d.id === first.id)).toBeUndefined();
    expect(store.documents.list()).toHaveLength(2);
  });

  it("delete() returns false for an unknown id", async () => {
    const store = await freshStore();
    expect(store.documents.delete("does-not-exist")).toBe(false);
    expect(store.documents.list()).toHaveLength(3);
  });
});

describe("store.dashboard", () => {
  it("summary().documentCount reflects only processed documents", async () => {
    const store = await freshStore();
    // Seed data has 2 processed + 1 processing document.
    expect(store.dashboard.summary().documentCount).toBe(2);
  });

  it("summary().documentCount updates after deleting a processed document", async () => {
    const store = await freshStore();
    const processed = store.documents.list().find((d) => d.status === "processed");
    expect(processed).toBeDefined();

    store.documents.delete(processed!.id);

    expect(store.dashboard.summary().documentCount).toBe(1);
  });

  it("summary() returns the expected shape", async () => {
    const store = await freshStore();
    const summary = store.dashboard.summary();

    expect(summary).toMatchObject({
      totalIncome: expect.any(Number),
      totalSpending: expect.any(Number),
      netSavings: expect.any(Number),
    });
    expect(summary.categoryBreakdown.length).toBeGreaterThan(0);
  });

  it("activity() returns the seeded transactions", async () => {
    const store = await freshStore();
    const activity = store.dashboard.activity();
    expect(activity.length).toBeGreaterThan(0);
    expect(activity[0]).toMatchObject({
      id: expect.any(String),
      description: expect.any(String),
      amount: expect.any(Number),
    });
  });
});
