import { Router } from "express";
import multer from "multer";
import { finSightStore } from "../lib/finSightStore.js";

const router = Router();
const upload = multer({ limits: { fileSize: 10 * 1024 * 1024 }, storage: multer.memoryStorage() });

router.get("/documents", (_req, res) => {
  res.json(finSightStore.documents.list());
});

router.post("/documents", upload.single("file"), (req, res) => {
  if (!req.file) {
    res.status(400).json({ error: "No file provided" });
    return;
  }
  const doc = finSightStore.documents.add(req.file.originalname, req.file.size);
  res.status(201).json(doc);
});

router.delete("/documents/:id", (req, res) => {
  const deleted = finSightStore.documents.delete(req.params.id);
  if (!deleted) {
    res.status(404).json({ error: "Document not found" });
    return;
  }
  res.status(204).send();
});

router.get("/chat/messages", (_req, res) => {
  res.json(finSightStore.chat.list());
});

router.post("/chat/messages", (req, res) => {
  const { content } = req.body as { content?: string };
  if (!content || typeof content !== "string" || !content.trim()) {
    res.status(400).json({ error: "Invalid message" });
    return;
  }
  const userMsg = finSightStore.chat.add("user", content.trim());
  const reply = finSightStore.chat.randomReply();
  const assistantMsg = finSightStore.chat.add("assistant", reply);
  res.status(201).json({ userMessage: userMsg, assistantMessage: assistantMsg });
});

router.get("/dashboard/summary", (_req, res) => {
  res.json(finSightStore.dashboard.summary());
});

router.get("/dashboard/activity", (_req, res) => {
  res.json(finSightStore.dashboard.activity());
});

export default router;
