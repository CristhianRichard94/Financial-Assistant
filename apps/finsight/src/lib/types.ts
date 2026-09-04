/**
 * Types for the Overview dashboard's real transaction data (see
 * services/rag-api/rag_api/schemas.py's DashboardSummaryOut/TransactionOut,
 * which these mirror field-for-field).
 *
 * Split out of store.ts (which now only holds the mock `Document` types
 * still used for the documents feature) since these no longer have any
 * backing mock implementation.
 */

export interface Transaction {
  id: string;
  description: string;
  category: string;
  amount: number;
  date: string;
}

export interface CategorySpending {
  category: string;
  amount: number;
  percentage: number;
}

export interface DashboardSummary {
  totalIncome: number;
  totalSpending: number;
  netSavings: number;
  incomeTrend: number;
  spendingTrend: number;
  savingsTrend: number;
  documentCount: number;
  totalDocumentCount: number;
  transactionCount: number;
  categoryBreakdown: CategorySpending[];
}

/**
 * Document/chat types, formerly defined alongside the mock `store` in
 * store.ts. The mock store implementation had no remaining consumers and was
 * removed; these types are still used across the documents and chat
 * features.
 */

export type DocumentStatus = "pending" | "processing" | "processed" | "error";
export type DocumentType = "pdf" | "csv" | "image";

export interface Document {
  id: string;
  name: string;
  type: DocumentType;
  size: number;
  status: DocumentStatus;
  uploadedAt: string;
  errorMessage?: string;
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  timestamp: string;
}
