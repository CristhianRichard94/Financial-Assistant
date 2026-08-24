"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import {
  TrendingUp,
  TrendingDown,
  Minus,
  AlertCircle,
  Loader2,
  Inbox,
  FileText,
  ShoppingCart,
  Home,
  Car,
  Music,
  Receipt,
  type LucideIcon,
} from "lucide-react";
import { cn, formatCurrency, formatDate } from "@/lib/utils";
import type { DashboardSummary, Transaction } from "@/lib/types";
import { Button } from "@/components/ui/button";
import {
  Empty,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
  EmptyDescription,
  EmptyContent,
} from "@/components/ui/empty";

function useDashboardSummary() {
  return useQuery<DashboardSummary>({
    queryKey: ["dashboard", "summary"],
    queryFn: async () => {
      const res = await fetch("/api/dashboard/summary");
      if (!res.ok) throw new Error("Failed to load dashboard summary");
      return res.json();
    },
    // Mirrors DocumentsView's useDocuments() polling pattern: keep polling
    // while the user has uploaded documents that haven't finished processing
    // yet (totalDocumentCount counts everything regardless of status, while
    // documentCount only counts completed ones - see rag_pipeline.dashboard).
    refetchInterval: (query) => {
      const data = query.state.data;
      if (!data) return false;
      return data.totalDocumentCount > 0 && data.documentCount === 0 ? 2000 : false;
    },
  });
}

function useActivity() {
  return useQuery<Transaction[]>({
    queryKey: ["dashboard", "activity"],
    queryFn: async () => {
      const res = await fetch("/api/dashboard/activity");
      if (!res.ok) throw new Error("Failed to load recent activity");
      return res.json();
    },
  });
}

// Category colors/icons have no backing API field (see src/lib/types.ts's
// CategorySpending/Transaction) - both are assigned client-side, at render
// time only, from a small fixed palette / keyword lookup.
const CATEGORY_COLOR_PALETTE = [
  "#6366f1",
  "#22c55e",
  "#f59e0b",
  "#8b5cf6",
  "#ec4899",
  "#14b8a6",
  "#94a3b8",
];

function getCategoryColor(index: number): string {
  return CATEGORY_COLOR_PALETTE[index % CATEGORY_COLOR_PALETTE.length];
}

function getCategoryIcon(category: string): LucideIcon {
  const normalized = category.toLowerCase();
  if (normalized.includes("grocery") || normalized.includes("groceries") || normalized.includes("food") || normalized.includes("dining")) {
    return ShoppingCart;
  }
  if (normalized.includes("rent") || normalized.includes("housing") || normalized.includes("mortgage")) {
    return Home;
  }
  if (normalized.includes("transport") || normalized.includes("uber") || normalized.includes("car") || normalized.includes("gas")) {
    return Car;
  }
  if (normalized.includes("subscription") || normalized.includes("entertainment") || normalized.includes("music")) {
    return Music;
  }
  return Receipt;
}

function StatCard({
  label,
  value,
  trend,
  docCount,
  positive,
}: {
  label: string;
  value: number;
  trend?: number;
  docCount?: number;
  positive?: boolean;
}) {
  // The trend badge is only ever shown in the happy-path state - both
  // `trend` and `positive` are omitted entirely for zero-transactions ($0
  // cards with no month-over-month comparison to show).
  const showTrend = trend !== undefined && positive !== undefined;
  const TrendIcon = trend! > 0 ? TrendingUp : trend! < 0 ? TrendingDown : Minus;
  const trendLabel = trend! > 0 ? `+${trend}%` : `${trend}%`;

  return (
    <div className="bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-xl p-6 flex flex-col gap-3 shadow-sm transition-all duration-200 ease-out hover:shadow-md hover:-translate-y-0.5">
      <div className="flex items-center justify-between">
        <span className="text-sm font-medium text-[hsl(var(--muted-foreground))]">{label}</span>
        {showTrend && (
          <span
            className={cn(
              "flex items-center gap-1 text-xs font-medium px-2 py-0.5 rounded-full",
              positive
                ? "bg-emerald-50 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-400"
                : "bg-red-50 text-red-600 dark:bg-red-500/15 dark:text-red-400"
            )}
          >
            <TrendIcon className="w-3 h-3" />
            {trendLabel} vs last month
          </span>
        )}
      </div>
      <p className="text-3xl font-bold tracking-tight text-[hsl(var(--foreground))]">
        {formatCurrency(value)}
      </p>
      {docCount !== undefined && (
        <p className="text-xs text-[hsl(var(--muted-foreground))]">
          Analyzed from {docCount} document{docCount !== 1 ? "s" : ""}
        </p>
      )}
    </div>
  );
}

function StatCardSkeleton() {
  return (
    <div className="bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-xl p-6 flex flex-col gap-3 shadow-sm animate-pulse">
      <div className="flex items-center justify-between">
        <div className="h-4 w-24 bg-[hsl(var(--muted))] rounded" />
        <div className="h-5 w-28 bg-[hsl(var(--muted))] rounded-full" />
      </div>
      <div className="h-9 w-32 bg-[hsl(var(--muted))] rounded" />
      <div className="h-3 w-40 bg-[hsl(var(--muted))] rounded" />
    </div>
  );
}

function RetryError({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <div
      role="alert"
      aria-live="polite"
      className="flex flex-col items-center justify-center gap-3 py-16 text-center"
    >
      <AlertCircle className="w-10 h-10 text-[hsl(var(--muted-foreground))]/40" />
      <p className="text-sm text-[hsl(var(--muted-foreground))]">{message}</p>
      <Button variant="outline" size="sm" onClick={onRetry}>
        Try again
      </Button>
    </div>
  );
}

function ProcessingNotice({ showLink }: { showLink: boolean }) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 py-16 text-center">
      <Loader2 className="w-10 h-10 text-[hsl(var(--muted-foreground))]/40 animate-spin" />
      <p className="text-sm text-[hsl(var(--muted-foreground))] max-w-sm">
        Your documents are still processing. This page will update automatically.
      </p>
      {showLink && (
        <Link
          href="/documents"
          className="text-sm font-medium text-[hsl(var(--primary))] underline underline-offset-4"
        >
          View documents
        </Link>
      )}
    </div>
  );
}

function ZeroTransactionsBanner() {
  return (
    <div className="flex items-center gap-3 px-4 py-3 bg-amber-50 dark:bg-amber-500/10 border border-amber-200 dark:border-amber-500/30 rounded-lg text-sm">
      <AlertCircle className="w-4 h-4 text-amber-600 dark:text-amber-400 shrink-0" />
      <span className="text-amber-700 dark:text-amber-400 flex-1">
        We couldn&apos;t find any transactions in your uploaded documents. FinSight currently
        extracts transactions from CSV bank exports only.{" "}
        <Link href="/documents" className="font-medium underline">
          Upload a CSV bank export
        </Link>
      </span>
    </div>
  );
}

function PanelEmptyMessage({ message }: { message: string }) {
  return (
    <div className="px-6 py-12 flex flex-col items-center justify-center text-center gap-2">
      <Inbox className="w-8 h-8 text-[hsl(var(--muted-foreground))]/40" />
      <p className="text-sm text-[hsl(var(--muted-foreground))]">{message}</p>
    </div>
  );
}

export function DashboardView() {
  const {
    data: summary,
    isLoading: summaryLoading,
    isError: summaryError,
    refetch: refetchSummary,
  } = useDashboardSummary();
  const {
    data: activity,
    isLoading: activityLoading,
    isError: activityError,
    refetch: refetchActivity,
  } = useActivity();

  const dashboardState =
    summaryLoading || summaryError
      ? null
      : summary
        ? summary.totalDocumentCount === 0
          ? "zero-docs"
          : summary.documentCount === 0
            ? "processing"
            : summary.transactionCount === 0
              ? "zero-transactions"
              : "happy"
        : null;

  return (
    <div className="p-6 lg:p-8 max-w-7xl mx-auto space-y-8">
      <div>
        <h1 className="text-2xl font-bold text-[hsl(var(--foreground))]">Overview</h1>
        <p className="text-sm text-[hsl(var(--muted-foreground))] mt-1">
          Your financial snapshot for this month
        </p>
      </div>

      {dashboardState === "zero-docs" ? (
        <Empty>
          <EmptyHeader>
            <EmptyMedia variant="icon">
              <FileText className="text-[hsl(var(--muted-foreground))]/40" />
            </EmptyMedia>
            <EmptyTitle>No financial data yet</EmptyTitle>
            <EmptyDescription>
              Upload a bank statement or CSV to see your overview.
            </EmptyDescription>
          </EmptyHeader>
          <EmptyContent>
            <Button asChild>
              <Link href="/documents">Upload documents</Link>
            </Button>
          </EmptyContent>
        </Empty>
      ) : dashboardState === "processing" ? (
        <div className="bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-xl shadow-sm">
          <ProcessingNotice showLink />
        </div>
      ) : (
        <>
          {dashboardState === "zero-transactions" && <ZeroTransactionsBanner />}

          {/* Summary Cards */}
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            {summaryLoading ? (
              <>
                <StatCardSkeleton />
                <StatCardSkeleton />
                <StatCardSkeleton />
              </>
            ) : summaryError ? (
              <div className="sm:col-span-3">
                <RetryError
                  message="Couldn't load your dashboard summary. Please try again."
                  onRetry={() => refetchSummary()}
                />
              </div>
            ) : summary ? (
              <>
                <StatCard
                  label="Total Income"
                  value={summary.totalIncome}
                  trend={dashboardState === "happy" ? summary.incomeTrend : undefined}
                  docCount={summary.documentCount}
                  positive={dashboardState === "happy" ? summary.incomeTrend >= 0 : undefined}
                />
                <StatCard
                  label="Total Spending"
                  value={summary.totalSpending}
                  trend={dashboardState === "happy" ? summary.spendingTrend : undefined}
                  positive={dashboardState === "happy" ? summary.spendingTrend <= 0 : undefined}
                />
                <StatCard
                  label="Net Savings"
                  value={summary.netSavings}
                  trend={dashboardState === "happy" ? summary.savingsTrend : undefined}
                  positive={dashboardState === "happy" ? summary.savingsTrend >= 0 : undefined}
                />
              </>
            ) : null}
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-5 gap-6">
            {/* Recent Activity */}
            <div className="lg:col-span-3 bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-xl shadow-sm">
              <div className="px-6 py-4 border-b border-[hsl(var(--border))]">
                <h2 className="font-semibold text-[hsl(var(--foreground))]">Recent Activity</h2>
              </div>
              <div className="divide-y divide-[hsl(var(--border))]">
                {activityLoading ? (
                  Array.from({ length: 5 }).map((_, i) => (
                    <div key={i} className="px-6 py-4 flex items-center gap-4 animate-pulse">
                      <div className="w-10 h-10 bg-[hsl(var(--muted))] rounded-full shrink-0" />
                      <div className="flex-1 space-y-2">
                        <div className="h-4 w-40 bg-[hsl(var(--muted))] rounded" />
                        <div className="h-3 w-24 bg-[hsl(var(--muted))] rounded" />
                      </div>
                      <div className="h-4 w-16 bg-[hsl(var(--muted))] rounded" />
                    </div>
                  ))
                ) : activityError ? (
                  <RetryError
                    message="Couldn't load recent activity. Please try again."
                    onRetry={() => refetchActivity()}
                  />
                ) : dashboardState === "zero-transactions" ? (
                  <PanelEmptyMessage message="No transactions found yet." />
                ) : (
                  activity?.map((tx) => {
                    const CategoryIcon = getCategoryIcon(tx.category);
                    return (
                      <div key={tx.id} className="px-6 py-4 flex items-center gap-4 hover:bg-[hsl(var(--muted))]/30 transition-colors duration-150">
                        <div className="w-10 h-10 bg-[hsl(var(--accent))] rounded-full flex items-center justify-center shrink-0">
                          <CategoryIcon className="w-4 h-4 text-[hsl(var(--accent-foreground))]" />
                        </div>
                        <div className="flex-1 min-w-0">
                          <p className="text-sm font-medium text-[hsl(var(--foreground))] truncate">{tx.description}</p>
                          <div className="flex items-center gap-2 mt-0.5">
                            <span className="text-xs text-[hsl(var(--muted-foreground))]">{formatDate(tx.date)}</span>
                            <span className="inline-flex items-center px-1.5 py-0.5 rounded-full text-xs font-medium bg-[hsl(var(--secondary))] text-[hsl(var(--secondary-foreground))]">
                              {tx.category}
                            </span>
                          </div>
                        </div>
                        <span
                          className={cn(
                            "text-sm font-semibold shrink-0",
                            tx.amount >= 0 ? "text-emerald-600 dark:text-emerald-400" : "text-[hsl(var(--foreground))]"
                          )}
                        >
                          {tx.amount >= 0 ? "+" : ""}
                          {formatCurrency(tx.amount)}
                        </span>
                      </div>
                    );
                  })
                )}
              </div>
            </div>

            {/* Spending by Category */}
            <div className="lg:col-span-2 bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-xl shadow-sm">
              <div className="px-6 py-4 border-b border-[hsl(var(--border))]">
                <h2 className="font-semibold text-[hsl(var(--foreground))]">Spending by Category</h2>
              </div>
              <div className="px-6 py-4 space-y-4">
                {summaryLoading ? (
                  Array.from({ length: 5 }).map((_, i) => (
                    <div key={i} className="space-y-2 animate-pulse">
                      <div className="flex justify-between">
                        <div className="h-3 w-24 bg-[hsl(var(--muted))] rounded" />
                        <div className="h-3 w-16 bg-[hsl(var(--muted))] rounded" />
                      </div>
                      <div className="h-2 bg-[hsl(var(--muted))] rounded-full" />
                    </div>
                  ))
                ) : summaryError ? (
                  <RetryError
                    message="Couldn't load category breakdown. Please try again."
                    onRetry={() => refetchSummary()}
                  />
                ) : dashboardState === "zero-transactions" ? (
                  <PanelEmptyMessage message="No spending data to show yet." />
                ) : (
                  summary?.categoryBreakdown.map((cat, index) => (
                    <div key={cat.category} className="space-y-1.5">
                      <div className="flex items-center justify-between">
                        <span className="text-sm text-[hsl(var(--foreground))]">{cat.category}</span>
                        <div className="flex items-center gap-2">
                          <span className="text-xs text-[hsl(var(--muted-foreground))]">{cat.percentage}%</span>
                          <span className="text-sm font-medium text-[hsl(var(--foreground))]">
                            {formatCurrency(cat.amount)}
                          </span>
                        </div>
                      </div>
                      <div className="h-2 bg-[hsl(var(--muted))] rounded-full overflow-hidden">
                        <div
                          className="h-full rounded-full transition-all"
                          style={{
                            width: `${cat.percentage}%`,
                            backgroundColor: getCategoryColor(index),
                          }}
                        />
                      </div>
                    </div>
                  ))
                )}
              </div>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
