"use client";

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState, KeyboardEvent } from "react";
import { Send, Bot, User, Loader2, FileText, AlertCircle, Clock } from "lucide-react";
import { nanoid } from "nanoid";
import { toast } from "sonner";
import { cn, formatDate } from "@/lib/utils";
import Link from "next/link";
import type { ChatMessage, Document } from "@/lib/store";

type OptimisticStatus = "pending" | "failed";

/** A chat message as rendered in the transcript. Optimistic user messages
 * carry a `status` while they are in flight or have failed to send; server
 * messages (and successfully-sent optimistic ones, once resolved) do not. */
type DisplayMessage = ChatMessage & { status?: OptimisticStatus };

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

function MessageBubble({
  msg,
  onRetryFailed,
}: {
  msg: DisplayMessage;
  onRetryFailed?: (msg: DisplayMessage) => void;
}) {
  const isUser = msg.role === "user";
  const isPending = isUser && msg.status === "pending";
  const isFailed = isUser && msg.status === "failed";

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
          onClick={isFailed ? () => onRetryFailed?.(msg) : undefined}
          onKeyDown={
            isFailed
              ? (e) => {
                  if (e.key === "Enter" || e.key === " ") {
                    e.preventDefault();
                    onRetryFailed?.(msg);
                  }
                }
              : undefined
          }
          role={isFailed ? "button" : undefined}
          tabIndex={isFailed ? 0 : undefined}
          aria-label={isFailed ? "Message not sent. Press Enter to edit and resend." : undefined}
          className={cn(
            "px-4 py-3 rounded-2xl text-sm leading-relaxed whitespace-pre-wrap",
            isUser
              ? "bg-[hsl(var(--primary))] text-white rounded-tr-sm"
              : "bg-[hsl(var(--card))] border border-[hsl(var(--border))] text-[hsl(var(--foreground))] rounded-tl-sm",
            isPending && "opacity-70",
            isFailed &&
              "ring-1 ring-red-400/70 dark:ring-red-500/60 cursor-pointer hover:opacity-90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[hsl(var(--ring))] focus-visible:ring-offset-2 transition"
          )}
        >
          {msg.content}
        </div>

        <div className={cn("flex items-center gap-1.5 flex-wrap", isUser && "justify-end")}>
          {isPending && (
            <span className="inline-flex items-center gap-1 text-[hsl(var(--muted-foreground))]">
              <Clock className="w-3 h-3" aria-hidden="true" />
              <span className="sr-only">Sending…</span>
            </span>
          )}

          <span className="text-xs text-[hsl(var(--muted-foreground))]">
            {new Date(msg.timestamp).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
          </span>

          {isFailed && (
            <span
              role="status"
              aria-label="Message not sent"
              className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-red-50 text-red-700 dark:bg-red-500/15 dark:text-red-400"
            >
              <AlertCircle className="w-3 h-3" aria-hidden="true" />
              Not sent
            </span>
          )}
        </div>
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
  const [optimisticMessages, setOptimisticMessages] = useState<DisplayMessage[]>([]);
  const bottomRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  // Ids of server messages that existed at the very first successful load —
  // true pre-existing history, never a valid match for a later optimistic
  // send. Captured once (not per-send): a per-send snapshot of "current
  // messages" is unsafe, because a *different* concurrent send's refetch can
  // resolve first and already include this send's own eventual message
  // (the API persists synchronously before replying), which would poison
  // that snapshot with the send's own id and make it un-matchable forever.
  const initialMessageIdsRef = useRef<Set<string> | null>(null);
  // Ids of server messages already matched to a resolved optimistic entry,
  // so the same server message can't be claimed twice by two entries with
  // identical content.
  const claimedIdsRef = useRef<Set<string>>(new Set());

  const hasDocuments =
    documents && documents.some((d) => d.status === "processed");

  // Server-fetched history plus any optimistic user messages that haven't
  // been resolved yet (still pending or failed). Successfully-sent
  // optimistic entries are removed once the server list has been refetched,
  // so they never appear twice. Sorted by timestamp so that unresolved
  // (pending/failed) local entries render at their true chronological
  // position rather than always trailing after the whole server list —
  // otherwise a failed send followed by a later successful one would show
  // the later message above the earlier, failed one. Array#sort is stable,
  // so entries sharing a timestamp keep their original relative order.
  const displayMessages: DisplayMessage[] = [...(messages ?? []), ...optimisticMessages].sort(
    (a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime()
  );
  const hasPendingSend = optimisticMessages.some((m) => m.status === "pending");

  const sendMutation = useMutation<unknown, Error, { clientId: string; content: string }>({
    mutationFn: async ({ content }) => {
      const res = await fetch("/api/chat/messages", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ content }),
      });
      if (!res.ok) throw new Error("Failed to send");
      return res.json();
    },
    onSuccess: async () => {
      // Refetch so the server list includes this message (and the assistant
      // reply). The reconciliation effect below is what actually drops the
      // matching optimistic entry once it sees the confirmed message —
      // including entries for *other* concurrent sends whose own mutate()
      // hasn't settled yet, which is what closes the duplicate-bubble race.
      await queryClient.invalidateQueries({ queryKey: ["chat", "messages"] });
    },
    onError: (_error, variables) => {
      setOptimisticMessages((prev) =>
        prev.map((m) => (m.id === variables.clientId ? { ...m, status: "failed" } : m))
      );
      toast.error("Your message couldn't be sent. Please try again.");
    },
  });

  // Reconcile pending optimistic entries against the server-fetched message
  // list. Runs on every update of either `messages` *or* `optimisticMessages`
  // — not just when a send's own mutate() call settles — for two reasons:
  // (1) the API persists the user's message synchronously, before it awaits
  // the (potentially slow) RAG call and responds to the POST, so a
  // *different*, faster concurrent send's refetch can reveal this message on
  // the server well before this send's own POST response reaches the client;
  // (2) React Query's structural sharing keeps the same `messages` reference
  // across refetches that return an identical body, so a new optimistic
  // entry created *after* such a refetch (already reflecting it) would never
  // get reconciled if this effect only re-ran on `messages` changes — it
  // also needs to re-check whenever a new entry is added. Matching on
  // content, scoped to messages that aren't part of pre-existing history and
  // haven't already been claimed by another entry, lets us drop the
  // optimistic bubble the moment the server confirms it, regardless of which
  // mutate() triggered the refetch.
  useEffect(() => {
    if (!messages) return;
    if (initialMessageIdsRef.current === null) {
      // First successful load: everything here is pre-existing history,
      // not a message any optimistic entry could ever legitimately match.
      initialMessageIdsRef.current = new Set(messages.map((m) => m.id));
      return;
    }
    setOptimisticMessages((prev) => {
      if (!prev.some((m) => m.status === "pending")) return prev;
      let changed = false;
      const next = prev.filter((m) => {
        if (m.status !== "pending") return true;
        const match = messages.find(
          (sm) =>
            sm.role === "user" &&
            sm.content === m.content &&
            !initialMessageIdsRef.current!.has(sm.id) &&
            !claimedIdsRef.current.has(sm.id)
        );
        if (!match) return true;
        claimedIdsRef.current.add(match.id);
        changed = true;
        return false;
      });
      return changed ? next : prev;
    });
  }, [messages, optimisticMessages]);

  const handleSend = () => {
    const content = input.trim();
    if (!content) return;
    // Guard against sending before the initial history fetch has settled,
    // since the reconciliation effect above only starts matching new
    // messages against optimistic entries once it has captured that first
    // load's ids as pre-existing history.
    if (isLoading) return;
    const clientId = nanoid();
    setOptimisticMessages((prev) => [
      ...prev,
      { id: clientId, role: "user", content, timestamp: new Date().toISOString(), status: "pending" },
    ]);
    setInput("");
    sendMutation.mutate({ clientId, content });
  };

  const handleRetryFailed = (msg: DisplayMessage) => {
    setInput(msg.content);
    textareaRef.current?.focus();
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, optimisticMessages]);

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
        ) : !displayMessages.length ? (
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
          displayMessages.map((msg) => (
            <MessageBubble key={msg.id} msg={msg} onRetryFailed={handleRetryFailed} />
          ))
        )}

        {hasPendingSend && <TypingIndicator />}
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
              className="w-full resize-none rounded-xl border border-[hsl(var(--border))] bg-[hsl(var(--background))] px-4 py-3 pr-12 text-sm placeholder:text-[hsl(var(--muted-foreground))] focus:outline-none focus:ring-2 focus:ring-[hsl(var(--ring))] disabled:opacity-50 transition-colors min-h-[48px] max-h-40"
              style={{ fieldSizing: "content" } as React.CSSProperties}
            />
          </div>
          <button
            onClick={handleSend}
            disabled={!input.trim() || isLoading}
            className="w-10 h-10 rounded-xl bg-[hsl(var(--primary))] text-white flex items-center justify-center hover:opacity-90 transition-opacity disabled:opacity-40 shrink-0"
          >
            <Send className="w-4 h-4" />
          </button>
        </div>
        <p className="text-xs text-[hsl(var(--muted-foreground))] mt-2 text-center max-w-4xl mx-auto">
          Enter to send · Shift+Enter for new line
        </p>
      </div>
    </div>
  );
}
