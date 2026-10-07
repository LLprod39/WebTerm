import { TerminalSquare } from "lucide-react";

import type { KubernetesPodRef } from "@/api";
import { localize } from "@/lib/i18n";

export function ExecStubPanel({
  lang,
  pod,
}: {
  lang: string;
  pod: KubernetesPodRef | null;
}) {
  const target = pod
    ? `${pod.namespace}/${pod.name}`
    : localize(lang, "pod не выбран", "no pod selected");

  return (
    <section data-ui-slot="cockpit-exec" className="flex min-h-0 flex-1 flex-col">
      <div className="border-b border-border/70 px-4 py-3.5 sm:px-5">
        <h3 className="text-sm font-semibold text-foreground">
          {localize(lang, "Exec", "Exec")}
        </h3>
        <p className="mt-0.5 truncate font-mono text-xs text-muted-foreground" title={target}>
          {target}
        </p>
      </div>

      <div className="flex flex-1 flex-col items-center justify-center gap-3 px-4 py-8 text-center sm:px-5">
        <span className="flex h-10 w-10 items-center justify-center rounded-lg border border-border bg-secondary/40 text-muted-foreground">
          <TerminalSquare className="h-5 w-5" aria-hidden />
        </span>
        <div className="max-w-sm space-y-1.5">
          <p className="text-sm font-medium text-foreground">
            {localize(lang, "Exec недоступен", "Exec unavailable")}
          </p>
          <p role="status" className="text-sm leading-6 text-muted-foreground">
            {localize(
              lang,
              "Выполнение команд в контейнере отключено в v1. Функция появится после подключения Exec API.",
              "Container exec is disabled in v1. It will be available after the Exec API is connected.",
            )}
          </p>
        </div>
      </div>
    </section>
  );
}
