"use client";

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useCallback, useState } from "react";
import { useDropzone } from "react-dropzone";
import { toast } from "sonner";
import {
  Upload,
  FileText,
  Table2,
  Image,
  Trash2,
  CheckCircle2,
  Clock,
  AlertCircle,
  Loader2,
  CloudUpload,
} from "lucide-react";
import { useTranslations } from "next-intl";
import { cn, formatDate, formatFileSize } from "@/lib/utils";
import type { Document } from "@/lib/types";

/** Maps a server-returned machine-readable error code (see the API route
 * handlers under `src/app/api/documents/`) to a translated user-facing
 * message, falling back to `errors.generic` for unknown codes (including
 * network failures, which never produce a code at all). */
function useErrorMessage() {
  const t = useTranslations("errors");
  return (code: string | undefined) => {
    if (code && t.has(code)) {
      return t(code);
    }
    return t("generic");
  };
}

async function extractErrorCode(res: Response): Promise<string | undefined> {
  try {
    const body = await res.json();
    return typeof body?.error === "string" ? body.error : undefined;
  } catch {
    return undefined;
  }
}

function useDocuments() {
  return useQuery<Document[]>({
    queryKey: ["documents"],
    queryFn: async () => {
      const res = await fetch("/api/documents");
      if (!res.ok) throw new Error("Failed to load documents");
      return res.json();
    },
    refetchInterval: (query) => {
      const data = query.state.data;
      if (!data) return false;
      const hasProcessing = data.some(
        (d) => d.status === "pending" || d.status === "processing"
      );
      return hasProcessing ? 2000 : false;
    },
  });
}

function DocTypeIcon({ type }: { type: Document["type"] }) {
  if (type === "pdf") return <FileText className="w-4 h-4 text-red-500 dark:text-red-400" />;
  if (type === "csv") return <Table2 className="w-4 h-4 text-emerald-500 dark:text-emerald-400" />;
  return <Image className="w-4 h-4 text-blue-500 dark:text-blue-400" />;
}

function StatusBadge({ status }: { status: Document["status"] }) {
  const t = useTranslations("documents.statuses");
  const map = {
    pending: { color: "bg-amber-50 text-amber-700 dark:bg-amber-500/15 dark:text-amber-400", icon: <Clock className="w-3 h-3" /> },
    processing: { color: "bg-blue-50 text-blue-700 dark:bg-blue-500/15 dark:text-blue-400", icon: <Loader2 className="w-3 h-3 animate-spin" /> },
    processed: { color: "bg-emerald-50 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-400", icon: <CheckCircle2 className="w-3 h-3" /> },
    error: { color: "bg-red-50 text-red-700 dark:bg-red-500/15 dark:text-red-400", icon: <AlertCircle className="w-3 h-3" /> },
  } as const;
  const { color, icon } = map[status];
  return (
    <span className={cn("inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium", color)}>
      {icon}
      {t(status)}
    </span>
  );
}

export function DocumentsView() {
  const t = useTranslations("documents");
  const getErrorMessage = useErrorMessage();
  const queryClient = useQueryClient();
  const { data: documents, isLoading, isError } = useDocuments();
  const [uploading, setUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);

  const deleteMutation = useMutation({
    mutationFn: async (id: string) => {
      const res = await fetch(`/api/documents/${id}`, { method: "DELETE" });
      if (!res.ok) {
        const code = await extractErrorCode(res);
        throw new Error(code);
      }
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["documents"] });
      toast.success(t("documentDeleted"));
    },
    onError: (error: Error) => toast.error(getErrorMessage(error.message)),
  });

  const onDrop = useCallback(
    async (acceptedFiles: File[]) => {
      const file = acceptedFiles[0];
      if (!file) return;
      if (file.size > 10 * 1024 * 1024) {
        toast.error(getErrorMessage("upload_too_large"));
        return;
      }
      setUploading(true);
      setUploadProgress(0);
      const interval = setInterval(() => {
        setUploadProgress((p) => Math.min(p + 15, 85));
      }, 100);
      try {
        const form = new FormData();
        form.append("file", file);
        const res = await fetch("/api/documents", { method: "POST", body: form });
        if (!res.ok) {
          const code = await extractErrorCode(res);
          throw new Error(code);
        }
        clearInterval(interval);
        setUploadProgress(100);
        await queryClient.invalidateQueries({ queryKey: ["documents"] });
        toast.success(t("uploadedSuccessfully", { fileName: file.name }));
      } catch (error) {
        clearInterval(interval);
        toast.error(getErrorMessage(error instanceof Error ? error.message : undefined));
      } finally {
        setTimeout(() => {
          setUploading(false);
          setUploadProgress(0);
        }, 600);
      }
    },
    [queryClient, getErrorMessage, t]
  );

  const { getRootProps, getInputProps, isDragActive, open } = useDropzone({
    onDrop,
    accept: {
      "application/pdf": [".pdf"],
      "text/csv": [".csv"],
      "image/jpeg": [".jpg", ".jpeg"],
      "image/png": [".png"],
    },
    maxSize: 10 * 1024 * 1024,
    noClick: true,
    multiple: false,
  });

  return (
    <div className="p-6 lg:p-8 max-w-5xl mx-auto space-y-8">
      <div>
        <h1 className="text-2xl font-bold text-[hsl(var(--foreground))]">{t("title")}</h1>
        <p className="text-sm text-[hsl(var(--muted-foreground))] mt-1">
          {t("subtitle")}
        </p>
      </div>

      {/* Drop zone */}
      <div
        {...getRootProps()}
        className={cn(
          "border-2 border-dashed rounded-xl p-10 text-center transition-all duration-200 ease-out cursor-default",
          isDragActive
            ? "border-[hsl(var(--primary))] bg-[hsl(var(--accent))]"
            : "border-[hsl(var(--border))] hover:border-[hsl(var(--primary))]/50 hover:bg-[hsl(var(--muted))]/30"
        )}
      >
        <input {...getInputProps()} />
        <div className="flex flex-col items-center gap-3">
          <div className={cn(
            "w-14 h-14 rounded-full flex items-center justify-center transition-colors",
            isDragActive ? "bg-[hsl(var(--primary))] text-white" : "bg-[hsl(var(--muted))] text-[hsl(var(--muted-foreground))]"
          )}>
            {uploading ? (
              <Loader2 className="w-6 h-6 animate-spin" />
            ) : (
              <CloudUpload className="w-6 h-6" />
            )}
          </div>
          {uploading ? (
            <div className="space-y-2 w-full max-w-xs">
              <p className="text-sm font-medium">{t("uploading")}</p>
              <div className="h-2 bg-[hsl(var(--muted))] rounded-full overflow-hidden">
                <div
                  className="h-full bg-[hsl(var(--primary))] rounded-full transition-all duration-300"
                  style={{ width: `${uploadProgress}%` }}
                />
              </div>
            </div>
          ) : isDragActive ? (
            <p className="text-sm font-medium text-[hsl(var(--primary))]">{t("dropToUpload")}</p>
          ) : (
            <>
              <div>
                <p className="text-sm font-medium text-[hsl(var(--foreground))]">
                  {t("dragDrop")}
                </p>
                <p className="text-xs text-[hsl(var(--muted-foreground))] mt-1">
                  {t("fileTypes")}
                </p>
              </div>
              <button
                type="button"
                onClick={open}
                className="flex items-center gap-2 px-4 py-2 text-sm font-medium bg-[hsl(var(--primary))] text-white rounded-lg hover:opacity-90 transition-opacity"
              >
                <Upload className="w-4 h-4" />
                {t("browseFiles")}
              </button>
            </>
          )}
        </div>
      </div>

      {/* Documents table */}
      <div className="bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-xl shadow-sm overflow-hidden">
        <div className="px-6 py-4 border-b border-[hsl(var(--border))]">
          <h2 className="font-semibold text-[hsl(var(--foreground))]">{t("uploadedDocuments")}</h2>
        </div>
        {isLoading ? (
          <div className="divide-y divide-[hsl(var(--border))]">
            {Array.from({ length: 3 }).map((_, i) => (
              <div key={i} className="flex items-center gap-4 px-6 py-4 animate-pulse">
                <div className="w-8 h-8 bg-[hsl(var(--muted))] rounded" />
                <div className="flex-1 space-y-2">
                  <div className="h-4 w-48 bg-[hsl(var(--muted))] rounded" />
                  <div className="h-3 w-32 bg-[hsl(var(--muted))] rounded" />
                </div>
                <div className="h-5 w-20 bg-[hsl(var(--muted))] rounded-full" />
                <div className="w-6 h-6 bg-[hsl(var(--muted))] rounded" />
              </div>
            ))}
          </div>
        ) : isError ? (
          <div className="px-6 py-16 text-center">
            <AlertCircle className="w-10 h-10 text-[hsl(var(--muted-foreground))]/40 mx-auto mb-3" />
            <p className="text-sm text-[hsl(var(--muted-foreground))]">{t("loadError")}</p>
          </div>
        ) : !documents?.length ? (
          <div className="px-6 py-16 text-center">
            <FileText className="w-10 h-10 text-[hsl(var(--muted-foreground))]/40 mx-auto mb-3" />
            <p className="text-sm text-[hsl(var(--muted-foreground))]">{t("noDocuments")}</p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-[hsl(var(--border))] bg-[hsl(var(--muted))]/30">
                  <th className="text-left px-6 py-3 font-medium text-[hsl(var(--muted-foreground))]">{t("name")}</th>
                  <th className="text-left px-6 py-3 font-medium text-[hsl(var(--muted-foreground))] hidden sm:table-cell">{t("dateAdded")}</th>
                  <th className="text-left px-6 py-3 font-medium text-[hsl(var(--muted-foreground))] hidden md:table-cell">{t("size")}</th>
                  <th className="text-left px-6 py-3 font-medium text-[hsl(var(--muted-foreground))]">{t("status")}</th>
                  <th className="px-6 py-3" />
                </tr>
              </thead>
              <tbody className="divide-y divide-[hsl(var(--border))]">
                {documents.map((doc) => (
                  <tr key={doc.id} className="hover:bg-[hsl(var(--muted))]/20 transition-colors duration-150">
                    <td className="px-6 py-4">
                      <div className="flex items-center gap-3">
                        <DocTypeIcon type={doc.type} />
                        <span className="font-medium text-[hsl(var(--foreground))] truncate max-w-[200px]">
                          {doc.name}
                        </span>
                      </div>
                    </td>
                    <td className="px-6 py-4 text-[hsl(var(--muted-foreground))] hidden sm:table-cell">
                      {formatDate(doc.uploadedAt)}
                    </td>
                    <td className="px-6 py-4 text-[hsl(var(--muted-foreground))] hidden md:table-cell">
                      {formatFileSize(doc.size)}
                    </td>
                    <td className="px-6 py-4">
                      <StatusBadge status={doc.status} />
                    </td>
                    <td className="px-6 py-4 text-right">
                      <button
                        onClick={() => deleteMutation.mutate(doc.id)}
                        disabled={deleteMutation.isPending}
                        className="p-1.5 rounded-lg hover:bg-red-50 hover:text-red-600 dark:hover:bg-red-500/15 dark:hover:text-red-400 text-[hsl(var(--muted-foreground))] transition-colors disabled:opacity-50"
                        aria-label={t("deleteDocument")}
                      >
                        <Trash2 className="w-4 h-4" />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
