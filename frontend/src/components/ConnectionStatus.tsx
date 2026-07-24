import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";

import { fetchAuthSession } from "@/lib/api";
import { localize, useI18n } from "@/lib/i18n";
import { cn } from "@/lib/utils";

export type ConnectionTone = "online" | "degraded" | "offline" | "unknown";

/**
 * Lightweight online/offline probe for the operator shell.
 * Combines browser navigator.onLine with a recent auth session fetch.
 */
export function useConnectionTone(): {
  tone: ConnectionTone;
  label: string;
  reconnecting: boolean;
} {
  const { lang } = useI18n();
  const [browserOnline, setBrowserOnline] = useState(
    typeof navigator === "undefined" ? true : navigator.onLine,
  );

  useEffect(() => {
    const on = () => setBrowserOnline(true);
    const off = () => setBrowserOnline(false);
    window.addEventListener("online", on);
    window.addEventListener("offline", off);
    return () => {
      window.removeEventListener("online", on);
      window.removeEventListener("offline", off);
    };
  }, []);

  const sessionQuery = useQuery({
    queryKey: ["auth", "session"],
    queryFn: fetchAuthSession,
    staleTime: 60_000,
    refetchInterval: browserOnline ? 90_000 : false,
    retry: false,
  });

  const tone: ConnectionTone = useMemo(() => {
    if (!browserOnline) return "offline";
    // While session is still loading, stay quiet (unknown) — never flash "no link".
    if (sessionQuery.isLoading || (sessionQuery.isFetching && !sessionQuery.data && !sessionQuery.isError)) {
      return "unknown";
    }
    if (sessionQuery.isError) return "degraded";
    if (sessionQuery.data?.authenticated) return "online";
    if (sessionQuery.data && !sessionQuery.data.authenticated) return "degraded";
    return "unknown";
  }, [
    browserOnline,
    sessionQuery.data,
    sessionQuery.isError,
    sessionQuery.isFetching,
    sessionQuery.isLoading,
  ]);

  const label =
    tone === "online"
      ? localize(lang, "Связь в норме", "Connected")
      : tone === "degraded"
        ? localize(lang, "Связь нестабильна", "Connection degraded")
        : tone === "offline"
          ? localize(lang, "Нет сети", "Offline")
          : localize(lang, "Проверка связи…", "Checking…");

  return {
    tone,
    label,
    reconnecting: !browserOnline || (sessionQuery.isFetching && tone !== "online"),
  };
}

export function ConnectionStatusDot({ className }: { className?: string }) {
  const { tone, label } = useConnectionTone();
  const color =
    tone === "online"
      ? "bg-success"
      : tone === "degraded"
        ? "bg-warning"
        : tone === "offline"
          ? "bg-destructive"
          : "bg-muted-foreground/50";

  return (
    <span
      className={cn("inline-flex items-center gap-1.5", className)}
      title={label}
    >
      <span className="relative flex h-2 w-2">
        {tone === "online" || tone === "unknown" ? (
          <span className={cn("absolute inline-flex h-full w-full animate-ping rounded-full opacity-40", color)} />
        ) : null}
        <span className={cn("relative inline-flex h-2 w-2 rounded-full", color)} />
      </span>
      <span className="sr-only">{label}</span>
    </span>
  );
}

export function ConnectionBanner() {
  const { lang } = useI18n();
  const { tone, reconnecting } = useConnectionTone();

  if (tone === "online" || tone === "unknown") return null;

  return (
    <div
      role="status"
      className={cn(
        "fixed inset-x-0 top-0 z-[60] flex justify-center px-3 pt-2 pointer-events-none",
      )}
    >
      <div
        className={cn(
          "pointer-events-auto rounded-full border px-3 py-1.5 text-xs font-medium shadow-elev-2 backdrop-blur",
          tone === "offline"
            ? "border-destructive/40 bg-destructive/95 text-destructive-foreground"
            : "border-warning/40 bg-warning/95 text-warning-foreground",
        )}
      >
        {tone === "offline"
          ? localize(lang, "Нет сети — жду переподключения…", "Offline — waiting to reconnect…")
          : reconnecting
            ? localize(lang, "Переподключаюсь…", "Reconnecting…")
            : localize(lang, "Связь нестабильна", "Connection degraded")}
      </div>
    </div>
  );
}
