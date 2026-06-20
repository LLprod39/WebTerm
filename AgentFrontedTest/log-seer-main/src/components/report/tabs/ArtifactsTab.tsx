import { artifacts } from "@/data/mockReport";
import { Button } from "@/components/ui/button";
import {
  FileText,
  FileArchive,
  FileCode2,
  FileTerminal,
  Download,
  Link2,
  type LucideIcon,
} from "lucide-react";
import { toast } from "sonner";

const iconFor = (name: string): LucideIcon => {
  if (name.endsWith(".pdf")) return FileText;
  if (name.endsWith(".tar.gz") || name.endsWith(".zip")) return FileArchive;
  if (name.endsWith(".json")) return FileCode2;
  return FileTerminal;
};

export function ArtifactsTab() {
  return (
    <div className="report-card overflow-hidden">
      <div className="flex items-center justify-between border-b border-border p-4 sm:p-5">
        <div>
          <h3 className="text-base font-semibold text-foreground">Артефакты анализа</h3>
          <p className="mt-0.5 text-sm text-muted-foreground">
            Файлы, собранные и сгенерированные агентом
          </p>
        </div>
        <Button
          variant="outline"
          className="h-10 gap-1.5"
          onClick={() => toast.success("Скачивание всех артефактов", { description: "25.5 MB" })}
        >
          <Download className="h-4 w-4" />
          <span className="hidden sm:inline">Скачать всё</span>
        </Button>
      </div>

      <ul className="divide-y divide-border">
        {artifacts.map((a) => {
          const Icon = iconFor(a.name);
          return (
            <li
              key={a.id}
              className="flex flex-col gap-3 p-4 transition-colors hover:bg-surface/60 sm:flex-row sm:items-center sm:p-5"
            >
              <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-lg bg-secondary text-primary">
                <Icon className="h-5 w-5" />
              </div>
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-mono text-sm font-medium text-foreground">{a.name}</span>
                  <span className="rounded border border-border bg-surface px-1.5 py-0.5 text-xs text-muted-foreground">
                    {a.type}
                  </span>
                </div>
                <p className="mt-1 text-sm text-muted-foreground">{a.description}</p>
                <p className="mt-1 flex flex-wrap gap-x-4 font-mono text-xs text-muted-foreground">
                  <span>{a.size}</span>
                  <span>{a.date}</span>
                </p>
              </div>
              <div className="flex shrink-0 gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  className="h-10 gap-1.5"
                  onClick={() => toast.success(`Скачивание ${a.name}`, { description: a.size })}
                >
                  <Download className="h-4 w-4" />
                  Скачать
                </Button>
                <Button
                  variant="ghost"
                  size="icon"
                  className="h-10 w-10"
                  aria-label="Скопировать ссылку"
                  onClick={() => toast.success("Ссылка на файл скопирована")}
                >
                  <Link2 className="h-4 w-4" />
                </Button>
              </div>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
