import type { ReactNode } from "react";
import { cn } from "@/lib/utils";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState, QueryStateBlock } from "@/components/ui/page-shell";

/**
 * Typed skeleton primitives — use these instead of ad-hoc spinners so loading
 * states mirror the shape of the content they replace.
 */

export function SkeletonList({ rows = 4, className }: { rows?: number; className?: string }) {
  return (
    <div className={cn("space-y-2", className)} aria-hidden>
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="flex items-center gap-3 rounded-lg border border-border/60 bg-surface-1 px-4 py-3">
          <Skeleton className="h-8 w-8 shrink-0 rounded-lg" />
          <div className="min-w-0 flex-1 space-y-2">
            <Skeleton className="h-3.5 w-1/3" />
            <Skeleton className="h-3 w-1/2" />
          </div>
          <Skeleton className="h-7 w-16 rounded-md" />
        </div>
      ))}
    </div>
  );
}

export function SkeletonCards({ count = 6, className }: { count?: number; className?: string }) {
  return (
    <div className={cn("grid gap-4 sm:grid-cols-2 xl:grid-cols-3", className)} aria-hidden>
      {Array.from({ length: count }).map((_, i) => (
        <div key={i} className="space-y-3 rounded-xl border border-border/60 bg-surface-1 p-5">
          <div className="flex items-center gap-3">
            <Skeleton className="h-9 w-9 rounded-lg" />
            <div className="flex-1 space-y-2">
              <Skeleton className="h-3.5 w-2/3" />
              <Skeleton className="h-3 w-1/3" />
            </div>
          </div>
          <Skeleton className="h-3 w-full" />
          <Skeleton className="h-3 w-4/5" />
        </div>
      ))}
    </div>
  );
}

export function SkeletonTable({ rows = 6, cols = 4, className }: { rows?: number; cols?: number; className?: string }) {
  return (
    <div className={cn("overflow-hidden rounded-xl border border-border/60 bg-surface-1", className)} aria-hidden>
      {Array.from({ length: rows }).map((_, r) => (
        <div key={r} className="flex items-center gap-4 border-b border-border/40 px-4 py-3 last:border-0">
          {Array.from({ length: cols }).map((_, c) => (
            <Skeleton key={c} className={cn("h-3.5", c === 0 ? "w-40" : "flex-1")} />
          ))}
        </div>
      ))}
    </div>
  );
}

export function SkeletonMetrics({ count = 4, className }: { count?: number; className?: string }) {
  return (
    <div className={cn("grid gap-4 sm:grid-cols-2 xl:grid-cols-4", className)} aria-hidden>
      {Array.from({ length: count }).map((_, i) => (
        <div key={i} className="space-y-3 rounded-xl border border-border/60 bg-surface-1 px-5 py-4">
          <Skeleton className="h-3 w-24" />
          <Skeleton className="h-8 w-16" />
          <Skeleton className="h-3 w-20" />
        </div>
      ))}
    </div>
  );
}

/**
 * ListState — the single wrapper for the three async states of a collection:
 * loading (skeleton), error (with retry), empty (EmptyState), else children.
 * Prefer this over hand-rolled spinners / bare error text so every list behaves
 * the same. Pass a `skeleton` matching the content shape (SkeletonList/Cards/Table).
 */
export function ListState({
  loading,
  error,
  isEmpty,
  onRetry,
  skeleton,
  empty,
  loadingText,
  errorText,
  children,
  className,
}: {
  loading?: boolean;
  error?: unknown;
  isEmpty?: boolean;
  onRetry?: () => void;
  /** Skeleton element shown while loading. Defaults to SkeletonList. */
  skeleton?: ReactNode;
  /** Empty-state element. Accepts an <EmptyState/> or any node. */
  empty?: ReactNode;
  loadingText?: string;
  errorText?: string;
  children: ReactNode;
  className?: string;
}) {
  if (loading) {
    return <div className={className}>{skeleton ?? <SkeletonList />}</div>;
  }
  return (
    <QueryStateBlock error={error} onRetry={onRetry} loadingText={loadingText} errorText={errorText} className={className}>
      {isEmpty ? (empty ?? <EmptyState title="" description="" />) : children}
    </QueryStateBlock>
  );
}
