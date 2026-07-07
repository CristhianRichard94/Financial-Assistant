"use client";

import { useQuery } from "@tanstack/react-query";
import { TrendingUp, TrendingDown, Minus, ArrowUpRight, ArrowDownRight } from "lucide-react";
import { cn, formatCurrency, formatDate } from "@/lib/utils";
import type { DashboardSummary, Transaction } from "@/lib/store";

function useDashboardSummary() {
  return useQuery<DashboardSummary>({
    queryKey: ["dashboard", "summary"],
    queryFn: async () => {
      const res = await fetch("/api/dashboard/summary");
      if (!res.ok) throw new Error("Failed to load dashboard summary");
      return res.json();
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

function StatCard({
  label,
  value,
  trend,
  docCount,
  positive,
}: {
  label: string;
  value: number;
  trend: number;
  docCount?: number;
  positive: boolean;
}) {
  const TrendIcon = trend > 0 ? TrendingUp : trend < 0 ? TrendingDown : Minus;
  const trendLabel = trend > 0 ? `+${trend}%` : `${trend}%`;

  return (
    <div className="bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-xl p-6 flex flex-col gap-3 shadow-sm transition-all duration-200 ease-out hover:shadow-md hover:-translate-y-0.5">
      <div className="flex items-center justify-between">
        <span className="text-sm font-medium text-[hsl(var(--muted-foreground))]">{label}</span>
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

export function DashboardView() {
  const { data: summary, isLoading: summaryLoading } = useDashboardSummary();
  const { data: activity, isLoading: activityLoading } = useActivity();

  return (
    <div className="p-6 lg:p-8 max-w-7xl mx-auto space-y-8">
      <div>
        <h1 className="text-2xl font-bold text-[hsl(var(--foreground))]">Overview</h1>
        <p className="text-sm text-[hsl(var(--muted-foreground))] mt-1">
          Your financial snapshot for this month
        </p>
      </div>

      {/* Summary Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        {summaryLoading ? (
          <>
            <StatCardSkeleton />
            <StatCardSkeleton />
            <StatCardSkeleton />
          </>
        ) : summary ? (
          <>
            <StatCard
              label="Total Income"
              value={summary.totalIncome}
              trend={summary.incomeTrend}
              docCount={summary.documentCount}
              positive={summary.incomeTrend >= 0}
            />
            <StatCard
              label="Total Spending"
              value={summary.totalSpending}
              trend={summary.spendingTrend}
              positive={summary.spendingTrend <= 0}
            />
            <StatCard
              label="Net Savings"
              value={summary.netSavings}
              trend={summary.savingsTrend}
              positive={summary.savingsTrend >= 0}
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
            ) : (
              activity?.map((tx) => (
                <div key={tx.id} className="px-6 py-4 flex items-center gap-4 hover:bg-[hsl(var(--muted))]/30 transition-colors duration-150">
                  <div className="w-10 h-10 bg-[hsl(var(--accent))] rounded-full flex items-center justify-center text-lg shrink-0">
                    {tx.icon}
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
              ))
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
            ) : (
              summary?.categoryBreakdown.map((cat) => (
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
                        backgroundColor: cat.color,
                      }}
                    />
                  </div>
                </div>
              ))
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
