import { useState } from "react";
import { TerminalSquare } from "lucide-react";

import type { KubernetesPodRef } from "@/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { localize } from "@/lib/i18n";

export function ExecStubPanel({
  lang,
  pod,
}: {
  lang: string;
  pod: KubernetesPodRef | null;
}) {
  const [command, setCommand] = useState("");
  const [output, setOutput] = useState("");

  const target = pod ? `${pod.namespace}/${pod.name}` : localize(lang, "pod не выбран", "no pod selected");

  return (
    <section data-ui-slot="cockpit-exec" className="flex min-h-0 flex-1 flex-col">
      <div className="border-b border-border/70 px-4 py-3.5 sm:px-5">
        <h3 className="text-sm font-semibold text-foreground">Exec</h3>
        <p className="mt-0.5 truncate font-mono text-xs text-muted-foreground" title={target}>
          {target}
        </p>
      </div>

      <div className="flex flex-1 flex-col gap-3 px-4 py-4 sm:px-5">
        <div className="grid gap-3 sm:grid-cols-[minmax(0,1fr)_auto] sm:items-end">
          <label className="grid gap-1.5 text-xs text-muted-foreground">
            {localize(lang, "Команда в контейнере", "Command in container")}
            <Input
              value={command}
              onChange={(event) => setCommand(event.target.value)}
              placeholder={localize(lang, "например: ls -la /var/log", "e.g. ls -la /var/log")}
              disabled={!pod}
              className="h-9 text-sm"
              aria-label={localize(lang, "Команда exec", "Exec command")}
            />
          </label>
          <Button
            type="button"
            variant="outline"
            size="sm"
            className="h-9 px-4"
            disabled={!pod}
            onClick={() => {
              setOutput(
                localize(
                  lang,
                  "Выполнение команд в контейнере будет доступно после подключения Exec API.",
                  "Container exec will be available after the Exec API is connected.",
                ),
              );
            }}
          >
            <TerminalSquare className="mr-2 h-4 w-4" />
            {localize(lang, "Выполнить", "Run")}
          </Button>
        </div>

        <div
          role="status"
          className="min-h-[8rem] flex-1 rounded-sm border border-dashed border-border bg-secondary/20 px-4 py-3 font-mono text-sm leading-6 text-muted-foreground"
        >
          {output ||
            localize(
              lang,
              "UI-заглушка: сетевой exec в v1 отключён.",
              "UI stub: network exec is disabled in v1.",
            )}
        </div>
      </div>
    </section>
  );
}
