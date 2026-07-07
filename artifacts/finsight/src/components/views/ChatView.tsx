"use client";

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState, KeyboardEvent } from "react";
import { Send, Bot, User, Loader2, FileText, AlertCircle } from "lucide-react";
import { cn, formatDate } from "@/lib/utils";
import Link from "next/link";
import type { ChatMessage, Document } from "@/lib/store";

function useMessages() {
  return useQuery<ChatMessage[]>({
    queryKey: ["chat", "messages"],
    queryFn: async () => {
      const res = await fetch("/api/chat/messages");
      if (!res.ok) throw new Error("Failed to load messages");
      return res.json();
    },
  });
}

function useDocuments() {
  return useQuery<Document[]>({
    queryKey: ["documents"],
    queryFn: async () => {
      const res = await fetch("/api/documents");
      if (!res.ok) throw new Error("Failed to load documents");
      return res.json();
    },
  });
}

function MessageBubble({ msg }: { msg: ChatMessage }) {
  const isUser = msg.role === "user";
  return (
    <div className={cn("flex gap-3 items-start", isUser && "flex-row-reverse")}>
      <div
        className={cn(
          "w-8 h-8 rounded-full shrink-0 flex items-center justify-center text-white",
          isUser ? "bg-[hsl(var(--primary))]" : "bg-[hsl(var(--sidebar))]"
        )}
      >
        {isUser ? <User className="w-4 h-4" /> : <Bot className="w-4 h-4" />}
      </div>
      <div className={cn("flex flex-col gap-1 max-w-[75%]", isUser && "items-end")}>
        <div
          className={cn(
            "px-4 py-3 rounded-2xl text-sm leading-relaxed whitespace-pre-wrap",
            isUser
              ? "bg-[hsl(var(--primary))] text-white rounded-tr-sm"
              : "bg-[hsl(var(--card))] border border-[hsl(var(--border))] text-[hsl(var(--foreground))] rounded-tl-sm"
          )}
        >
          {msg.content}
        </div>
        <span className="text-xs text-[hsl(var(--muted-foreground))]">
          {new Date(msg.timestamp).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
        </span>
      </div>
    </div>
  );
}

function TypingIndicator() {
  return (
    <div className="flex gap-3 items-start">
      <div className="w-8 h-8 rounded-full bg-[hsl(var(--sidebar))] flex items-center justify-center text-white shrink-0">
        <Bot className="w-4 h-4" />
      </div>
      <div className="px-4 py-3 rounded-2xl rounded-tl-sm bg-[hsl(var(--card))] border border-[hsl(var(--border))]">
        <div className="flex gap-1 items-center h-4">
          {[0, 1, 2].map((i) => (
            <span
              key={i}
              className="w-2 h-2 bg-[hsl(var(--muted-foreground))]/50 rounded-full animate-bounce"
              style={{ animationDelay: `${i * 150}ms` }}
            />
          ))}
        </div>
      </div>
    </div>
  );
}

export function ChatView() {
  const queryClient = useQueryClient();
  const { data: messages, isLoading, isError } = useMessages();
  const { data: documents } = useDocuments();
  const [input, setInput] = useState("");
  const bottomRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const hasDocuments =
    documents && documents.some((d) => d.status === "processed");

  const sendMutation = useMutation({
    mutationFn: async (content: string) => {
      const res = await fetch("/api/chat/messages", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ content }),
      });
      if (!res.ok) throw new Error("Failed to send");
      return res.json();
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["chat", "messages"] });
    },
  });

  const handleSend = () => {
    const msg = input.trim();
    if (!msg || sendMutation.isPending) return;
    setInput("");
    sendMutation.mutate(msg);
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, sendMutation.isPending]);

  return (
    <div className="flex flex-col h-full bg-[hsl(var(--background))]">
      {/* Header */}
      <div className="px-6 py-4 border-b border-[hsl(var(--border))] bg-[hsl(var(--card))] shrink-0">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-full bg-[hsl(var(--sidebar))] flex items-center justify-center">
            <Bot className="w-5 h-5 text-white" />
          </div>
          <div>
            <p className="font-semibold text-[hsl(var(--foreground))] text-sm">FinSight AI</p>
            <p className="text-xs text-[hsl(var(--muted-foreground))]">
              {hasDocuments
                ? "Ready to analyze your finances"
                : "Upload documents to unlock full analysis"}
            </p>
          </div>
        </div>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-4 lg:px-8 py-6 space-y-6">
        {isLoading ? (
          <div className="flex justify-center py-12">
            <Loader2 className="w-6 h-6 animate-spin text-[hsl(var(--muted-foreground))]" />
          </div>
        ) : isError ? (
          <div className="flex flex-col items-center justify-center h-full py-16 text-center">
            <AlertCircle className="w-10 h-10 text-[hsl(var(--muted-foreground))]/40 mb-3" />
            <p className="text-sm text-[hsl(var(--muted-foreground))]">Couldn&apos;t load messages. Please try again.</p>
          </div>
        ) : !messages?.length ? (
          <div className="flex flex-col items-center justify-center h-full py-16 text-center space-y-4">
            <div className="w-16 h-16 rounded-full bg-[hsl(var(--accent))] flex items-center justify-center">
              <Bot className="w-8 h-8 text-[hsl(var(--accent-foreground))]" />
            </div>
            <div>
              <h3 className="font-semibold text-[hsl(var(--foreground))]">Welcome to FinSight</h3>
              <p className="text-sm text-[hsl(var(--muted-foreground))] mt-1 max-w-sm">
                Ask me anything about your finances. I can analyze income, spending patterns, and more.
              </p>
            </div>
          </div>
        ) : (
          messages.map((msg) => <MessageBubble key={msg.id} msg={msg} />)
        )}

        {sendMutation.isPending && <TypingIndicator />}
        <div ref={bottomRef} />
      </div>

      {/* No documents callout */}
      {!hasDocuments && !isLoading && (
        <div className="mx-4 lg:mx-8 mb-3 flex items-center gap-3 px-4 py-3 bg-amber-50 dark:bg-amber-500/10 border border-amber-200 dark:border-amber-500/30 rounded-lg text-sm">
          <AlertCircle className="w-4 h-4 text-amber-600 dark:text-amber-400 shrink-0" />
          <span className="text-amber-700 dark:text-amber-400 flex-1">
            No processed documents yet.{" "}
            <Link href="/documents" className="font-medium underline">
              Upload a document
            </Link>{" "}
            to enable full financial analysis.
          </span>
        </div>
      )}

      {/* Input */}
      <div className="px-4 lg:px-8 py-4 border-t border-[hsl(var(--border))] bg-[hsl(var(--card))] shrink-0">
        <div className="flex gap-3 items-end max-w-4xl mx-auto">
          <div className="flex-1 relative">
            <textarea
              ref={textareaRef}
              rows={1}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder={
                hasDocuments
                  ? "Ask me about your finances…"
                  : "Ask me anything…"
              }
              disabled={sendMutation.isPending}
              className="w-full resize-none rounded-xl border border-[hsl(var(--border))] bg-[hsl(var(--background))] px-4 py-3 pr-12 text-sm placeholder:text-[hsl(var(--muted-foreground))] focus:outline-none focus:ring-2 focus:ring-[hsl(var(--ring))] disabled:opacity-50 transition-colors min-h-[48px] max-h-40"
              style={{ fieldSizing: "content" } as React.CSSProperties}
            />
          </div>
          <button
            onClick={handleSend}
            disabled={!input.trim() || sendMutation.isPending}
            className="w-10 h-10 rounded-xl bg-[hsl(var(--primary))] text-white flex items-center justify-center hover:opacity-90 transition-opacity disabled:opacity-40 shrink-0"
          >
            {sendMutation.isPending ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <Send className="w-4 h-4" />
            )}
          </button>
        </div>
        <p className="text-xs text-[hsl(var(--muted-foreground))] mt-2 text-center max-w-4xl mx-auto">
          Enter to send · Shift+Enter for new line
        </p>
      </div>
    </div>
  );
}
