import type { Document } from "@/lib/store";

/**
 * Server-side client for the Python rag-api service (services/rag-api).
 *
 * This must only ever be imported from server-side code (Next.js Route
 * Handlers) - the rag-api base URL is never exposed to the browser, and
 * rag-api itself has no CORS configuration since it expects to be called
 * server-to-server only.
 */

export class RagApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "RagApiError";
    this.status = status;
  }
}

export interface QuerySource {
  filename: string;
  similarity: number;
}

export interface QueryResult {
  answer: string;
  sources: QuerySource[];
}

function getBaseUrl(): string {
  const baseUrl = process.env.RAG_API_BASE_URL;
  if (!baseUrl) {
    throw new Error(
      "RAG_API_BASE_URL is not set. Copy artifacts/finsight/.env.example to " +
        ".env.local and set it to the rag-api service's URL (e.g. http://localhost:8000)."
    );
  }
  return baseUrl.replace(/\/$/, "");
}

function getInternalApiKey(): string {
  const key = process.env.RAG_API_INTERNAL_KEY;
  if (!key) {
    throw new Error(
      "RAG_API_INTERNAL_KEY is not set. Copy artifacts/finsight/.env.example to " +
        ".env.local and set it to the same value configured as rag-api's INTERNAL_API_KEY."
    );
  }
  return key;
}

/** Every request to rag-api must carry this shared-secret header - see
 * rag_api/auth.py. This is defense-in-depth on top of network isolation
 * (rag-api's ALB is internal-only in production). */
function internalAuthHeaders(): Record<string, string> {
  return { "X-Internal-Api-Key": getInternalApiKey() };
}

async function extractErrorMessage(res: Response): Promise<string> {
  try {
    const body = await res.json();
    return body?.detail ?? body?.error ?? res.statusText;
  } catch {
    return res.statusText;
  }
}

async function assertOk(res: Response, action: string): Promise<void> {
  if (!res.ok) {
    const message = await extractErrorMessage(res);
    throw new RagApiError(res.status, `Failed to ${action}: ${message}`);
  }
}

export async function listDocuments(): Promise<Document[]> {
  const res = await fetch(`${getBaseUrl()}/documents`, {
    cache: "no-store",
    headers: internalAuthHeaders(),
  });
  await assertOk(res, "list documents");
  return res.json();
}

export async function uploadDocument(formData: FormData): Promise<Document> {
  const res = await fetch(`${getBaseUrl()}/upload`, {
    method: "POST",
    headers: internalAuthHeaders(),
    body: formData,
  });
  await assertOk(res, "upload document");
  return res.json();
}

export async function deleteDocument(id: string): Promise<void> {
  const res = await fetch(`${getBaseUrl()}/documents/${id}`, {
    method: "DELETE",
    headers: internalAuthHeaders(),
  });
  await assertOk(res, "delete document");
}

export async function queryRag(question: string): Promise<QueryResult> {
  const res = await fetch(`${getBaseUrl()}/query`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...internalAuthHeaders() },
    body: JSON.stringify({ question }),
  });
  await assertOk(res, "query documents");
  return res.json();
}
