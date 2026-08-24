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
  errorMessage?: string;
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  timestamp: string;
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
};
