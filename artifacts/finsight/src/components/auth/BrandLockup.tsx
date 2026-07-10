import { TrendingUp } from "lucide-react";

/** Shared brand header for the login page and the session-resolving loading
 * screen (`src/app/loading.tsx`) - kept in one place so both stay visually
 * identical, which is required so neither ever reads as a "flash" of the
 * other. */
export function BrandLockup() {
  return (
    <div className="flex flex-col items-center gap-3 text-center">
      <div className="flex items-center gap-3">
        <div className="w-12 h-12 rounded-xl bg-[hsl(var(--primary))] flex items-center justify-center shrink-0">
          <TrendingUp className="w-6 h-6 text-white" />
        </div>
        <span className="font-semibold text-2xl tracking-tight text-[hsl(var(--foreground))]">
          FinSight
        </span>
      </div>
      <p className="text-sm text-[hsl(var(--muted-foreground))]">AI-powered finance assistant</p>
    </div>
  );
}
