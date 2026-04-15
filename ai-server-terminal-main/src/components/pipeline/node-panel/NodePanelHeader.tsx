import type { ReactNode } from "react";
import { Copy, X } from "lucide-react";

import { Button } from "@/components/ui/button";

import { t, type NodePanelLang } from "./shared";

type NodePanelHeaderProps = {
  lang: NodePanelLang;
  icon: ReactNode;
  title: string;
  breadcrumb: string;
  nodeId: string;
  onDuplicate: () => void;
  onClose: () => void;
};

export function NodePanelHeader({
  lang,
  icon,
  title,
  breadcrumb,
  nodeId,
  onDuplicate,
  onClose,
}: NodePanelHeaderProps) {
  return (
    <div className="border-b border-border/70 bg-background/95 px-4 py-4">
      <div className="flex items-start justify-between gap-3">
        <div className="flex min-w-0 items-start gap-3">
          <div className="flex h-11 w-11 items-center justify-center rounded-2xl border border-border/70 bg-muted/40 shadow-sm">
            {icon}
          </div>
          <div className="min-w-0 space-y-1">
            <p className="text-[11px] uppercase tracking-[0.16em] text-muted-foreground">
              {breadcrumb}
            </p>
            <h2 className="truncate text-base font-semibold leading-tight text-foreground">
              {title}
            </h2>
            <p className="truncate text-xs text-muted-foreground">{nodeId}</p>
          </div>
        </div>

        <div className="flex items-center gap-1">
          <Button
            type="button"
            size="icon"
            variant="ghost"
            className="h-9 w-9 rounded-xl"
            onClick={onDuplicate}
            aria-label={t(lang, "Дублировать ноду", "Duplicate node")}
          >
            <Copy className="h-4 w-4" />
          </Button>
          <Button
            type="button"
            size="icon"
            variant="ghost"
            className="h-9 w-9 rounded-xl"
            onClick={onClose}
            aria-label={t(lang, "Закрыть панель", "Close panel")}
          >
            <X className="h-4 w-4" />
          </Button>
        </div>
      </div>
    </div>
  );
}
