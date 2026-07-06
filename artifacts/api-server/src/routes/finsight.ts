import { Router } from "express";
import multer from "multer";
import { finSightStore } from "../lib/finSightStore.js";
import {
  RagApiError,
  deleteDocument,
  listDocuments,
  queryRag,
  uploadDocument,
} from "../lib/ragApiClient.js";

const router = Router();
const upload = multer({ limits: { fileSize: 10 * 1024 * 1024 }, storage: multer.memoryStorage() });

const FALLBACK_REPLY =
  "Sorry, I couldn't process that question right now. Please try again in a moment.";

router.get("/documents", async (_req, res) => {
  try {
    const documents = await listDocuments();
    res.json(documents);
  } catch (error) {
    console.error("Failed to list documents via rag-api:", error);
    const status = error instanceof RagApiError ? error.status : 500;
    res.status(status).json({ error: "Failed to list documents" });
  }
});

router.post("/documents", upload.single("file"), async (req, res) => {
  if (!req.file) {
    res.status(400).json({ error: "No file provided" });
    return;
  }
  try {
    const formData = new FormData();
    const blob = new Blob([Uint8Array.from(req.file.buffer)], {
      type: req.file.mimetype || "application/octet-stream",
    });
    formData.append("file", blob, req.file.originalname);
    const doc = await uploadDocument(formData);
    res.status(201).json(doc);
  } catch (error) {
    console.error("Failed to upload document via rag-api:", error);
    const status = error instanceof RagApiError ? error.status : 500;
    res.status(status).json({ error: "Upload failed" });
  }
});

router.delete("/documents/:id", async (req, res) => {
  try {
    await deleteDocument(req.params.id);
    res.status(204).send();
  } catch (error) {
    if (error instanceof RagApiError && error.status === 404) {
      res.status(404).json({ error: "Document not found" });
      return;
    }
    console.error("Failed to delete document via rag-api:", error);
    res.status(500).json({ error: "Failed to delete document" });
  }
});

router.get("/chat/messages", (_req, res) => {
  res.json(finSightStore.chat.list());
});

router.post("/chat/messages", async (req, res) => {
  const { content } = req.body as { content?: string };
  if (!content || typeof content !== "string" || !content.trim()) {
    res.status(400).json({ error: "Invalid message" });
    return;
  }
  const userMsg = finSightStore.chat.add("user", content.trim());

  let replyContent = FALLBACK_REPLY;
  try {
    const result = await queryRag(content.trim());
    replyContent = result.answer;
  } catch (error) {
    console.error("Failed to query rag-api for chat reply:", error);
  }

  const assistantMsg = finSightStore.chat.add("assistant", replyContent);
  res.status(201).json({ userMessage: userMsg, assistantMessage: assistantMsg });
});

router.get("/dashboard/summary", (_req, res) => {
  res.json(finSightStore.dashboard.summary());
});

router.get("/dashboard/activity", (_req, res) => {
  res.json(finSightStore.dashboard.activity());
});

export default router;
