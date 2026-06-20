import { Button } from "@/components/ui/button";
import { artifacts } from "@/data/mockReport";
import { FileText, FileArchive, FileCode2, FileTerminal, Download, ArrowRight } from "lucide-react";
import { toast } from "sonner";

const iconFor = (name: string) => {
  if (name.endsWith(".pdf")) return FileText;
  if (name.endsWith(".tar.gz") || name.endsWith(".zip")) return FileArchive;
  if (name.endsWith(".json")) return FileCode2;
  return FileTerminal;
};

interface ArtifactsCardProps {
  onViewAll: () => void;
}

export function ArtifactsCard({ onViewAll }: ArtifactsCardProps) {
  return (
    <div className="report-card p-5">
      <div className="flex items-center justify-between">
        <h3 className="text-base font-semibold text-foreground">Артефакты</h3>
        <span className="text-xs text-muted-foreground">{artifacts.length} файла</span>
      </div>

      <ul className="mt-4 space-y-2">
        {artifacts.map((a) => {
          const Icon = iconFor(a.name);
          return (
            <li
              key={a.id}
              className="flex items-center gap-3 rounded-lg border border-border bg-surface/60 p-2.5 transition-colors hover:border-primary/30"
            >
              <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-md bg-secondary text-muted-foreground">
                <Icon className="h-[18px] w-[18px]" />
              </div>
              <div className="min-w-0 flex-1">
                <p className="truncate font-mono text-sm font-medium text-foreground">{a.name}</p>
                <p className="text-xs text-muted-foreground">{a.size}</p>
              </div>
              <Button
                variant="ghost"
                size="icon"
                className="h-9 w-9 shrink-0"
                aria-label={`Скачать ${a.name}`}
                onClick={() => toast.success(`Скачивание ${a.name}`, { description: a.size })}
              >
                <Download className="h-4 w-4" />
              </Button>
            </li>
          );
        })}
      </ul>

      <Button variant="outline" className="mt-4 h-10 w-full gap-1.5" onClick={onViewAll}>
        Все артефакты
        <ArrowRight className="h-4 w-4" />
      </Button>
    </div>
  );
}
