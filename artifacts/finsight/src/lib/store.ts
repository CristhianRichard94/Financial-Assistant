import { nanoid } from "nanoid";

export type DocumentStatus = "pending" | "processing" | "processed" | "error";
export type DocumentType = "pdf" | "csv" | "image";

export interface Document {
  id: string;
  name: string;
  type: DocumentType;
  size: number;
  status: DocumentStatus;
  uploadedAt: string;
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  timestamp: string;
}

export interface Transaction {
  id: string;
  description: string;
  category: string;
  amount: number;
  date: string;
  icon: string;
}

export interface CategorySpending {
  category: string;
  amount: number;
  percentage: number;
  color: string;
}

export interface DashboardSummary {
  totalIncome: number;
  totalSpending: number;
  netSavings: number;
  incomeTrend: number;
  spendingTrend: number;
  savingsTrend: number;
  documentCount: number;
  categoryBreakdown: CategorySpending[];
}

function getDocumentType(filename: string): DocumentType {
  const ext = filename.split(".").pop()?.toLowerCase();
  if (ext === "pdf") return "pdf";
  if (ext === "csv") return "csv";
  return "image";
}

const documents: Document[] = [
  {
    id: nanoid(),
    name: "bank_statement_may2025.pdf",
    type: "pdf",
    size: 248320,
    status: "processed",
    uploadedAt: new Date(Date.now() - 2 * 24 * 60 * 60 * 1000).toISOString(),
  },
  {
    id: nanoid(),
    name: "transactions_q1.csv",
    type: "csv",
    size: 48500,
    status: "processed",
    uploadedAt: new Date(Date.now() - 5 * 24 * 60 * 60 * 1000).toISOString(),
  },
  {
    id: nanoid(),
    name: "receipt_whole_foods.jpg",
    type: "image",
    size: 1240000,
    status: "processing",
    uploadedAt: new Date(Date.now() - 30 * 60 * 1000).toISOString(),
  },
];

const chatMessages: ChatMessage[] = [
  {
    id: nanoid(),
    role: "assistant",
    content:
      "Hello! I'm your FinSight assistant. I've analyzed your uploaded documents and I'm ready to help. What would you like to know about your finances?",
    timestamp: new Date(Date.now() - 10 * 60 * 1000).toISOString(),
  },
];

export const store = {
  documents: {
    list: (): Document[] => [...documents],
    add: (name: string, size: number): Document => {
      const doc: Document = {
        id: nanoid(),
        name,
        type: getDocumentType(name),
        size,
        status: "pending",
        uploadedAt: new Date().toISOString(),
      };
      documents.push(doc);
      setTimeout(() => {
        const found = documents.find((d) => d.id === doc.id);
        if (found) found.status = "processing";
        setTimeout(() => {
          const f = documents.find((d) => d.id === doc.id);
          if (f) f.status = "processed";
        }, 3000);
      }, 1000);
      return doc;
    },
    delete: (id: string): boolean => {
      const idx = documents.findIndex((d) => d.id === id);
      if (idx === -1) return false;
      documents.splice(idx, 1);
      return true;
    },
  },
  chat: {
    list: (): ChatMessage[] => [...chatMessages],
    add: (role: "user" | "assistant", content: string): ChatMessage => {
      const msg: ChatMessage = {
        id: nanoid(),
        role,
        content,
        timestamp: new Date().toISOString(),
      };
      chatMessages.push(msg);
      return msg;
    },
  },
  dashboard: {
    summary: (): DashboardSummary => ({
      totalIncome: 8450,
      totalSpending: 5520,
      netSavings: 2930,
      incomeTrend: 3.2,
      spendingTrend: -1.8,
      savingsTrend: 12.4,
      documentCount: documents.filter((d) => d.status === "processed").length,
      categoryBreakdown: [
        { category: "Housing", amount: 2100, percentage: 38, color: "#6366f1" },
        { category: "Groceries & Dining", amount: 680, percentage: 12, color: "#22c55e" },
        { category: "Transportation", amount: 420, percentage: 8, color: "#f59e0b" },
        { category: "Subscriptions", amount: 185, percentage: 3, color: "#8b5cf6" },
        { category: "Healthcare", amount: 310, percentage: 6, color: "#ec4899" },
        { category: "Entertainment", amount: 230, percentage: 4, color: "#14b8a6" },
        { category: "Other", amount: 1595, percentage: 29, color: "#94a3b8" },
      ],
    }),
    activity: (): Transaction[] => [
      {
        id: nanoid(),
        description: "Whole Foods Market",
        category: "Groceries",
        amount: -87.43,
        date: new Date(Date.now() - 1 * 24 * 60 * 60 * 1000).toISOString(),
        icon: "🛒",
      },
      {
        id: nanoid(),
        description: "Direct Deposit — Employer",
        category: "Income",
        amount: 4225.0,
        date: new Date(Date.now() - 2 * 24 * 60 * 60 * 1000).toISOString(),
        icon: "💰",
      },
      {
        id: nanoid(),
        description: "Spotify Premium",
        category: "Subscriptions",
        amount: -11.99,
        date: new Date(Date.now() - 3 * 24 * 60 * 60 * 1000).toISOString(),
        icon: "🎵",
      },
      {
        id: nanoid(),
        description: "Uber",
        category: "Transportation",
        amount: -24.5,
        date: new Date(Date.now() - 3 * 24 * 60 * 60 * 1000).toISOString(),
        icon: "🚗",
      },
      {
        id: nanoid(),
        description: "Amazon",
        category: "Shopping",
        amount: -134.99,
        date: new Date(Date.now() - 4 * 24 * 60 * 60 * 1000).toISOString(),
        icon: "📦",
      },
      {
        id: nanoid(),
        description: "Netflix",
        category: "Subscriptions",
        amount: -17.99,
        date: new Date(Date.now() - 5 * 24 * 60 * 60 * 1000).toISOString(),
        icon: "🎬",
      },
      {
        id: nanoid(),
        description: "Chipotle",
        category: "Dining",
        amount: -18.75,
        date: new Date(Date.now() - 5 * 24 * 60 * 60 * 1000).toISOString(),
        icon: "🌯",
      },
    ],
  },
};
