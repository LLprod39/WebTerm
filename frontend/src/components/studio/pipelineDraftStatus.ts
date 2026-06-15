import {
  AlertTriangle,
  HelpCircle,
  ShieldCheck,
  XCircle,
  type LucideIcon,
} from "lucide-react";

import { localize } from "@/lib/i18n";
import type { StudioPipelineAssistantResponse } from "@/lib/studioPipelineDraftsApi";

export type PipelineDraftStatus = {
  label: string;
  className: string;
  icon: LucideIcon;
};

export function getPipelineDraftStatus(
  response: StudioPipelineAssistantResponse | null,
  lang: string,
): PipelineDraftStatus {
  if (!response) {
    return {
      label: localize(lang, "Ожидает запроса", "Waiting"),
      className: "border-border bg-secondary/40 text-muted-foreground",
      icon: HelpCircle,
    };
  }
  if (response.validation?.ok === false) {
    return {
      label: localize(lang, "Нужна правка", "Needs fix"),
      className: "border-red-500/25 bg-red-500/10 text-red-300",
      icon: XCircle,
    };
  }
  if (response.risk?.level === "dangerous") {
    return {
      label: localize(lang, "Опасное действие", "Dangerous"),
      className: "border-red-500/25 bg-red-500/10 text-red-300",
      icon: AlertTriangle,
    };
  }
  if (response.risk?.level === "review") {
    return {
      label: localize(lang, "Нужен review", "Review"),
      className: "border-amber-500/25 bg-amber-500/10 text-amber-300",
      icon: AlertTriangle,
    };
  }
  if (response.questions?.length) {
    return {
      label: localize(lang, "Есть вопросы", "Questions"),
      className: "border-sky-500/25 bg-sky-500/10 text-sky-300",
      icon: HelpCircle,
    };
  }
  return {
    label: localize(lang, "DAG проверен", "DAG verified"),
    className: "border-emerald-500/25 bg-emerald-500/10 text-emerald-300",
    icon: ShieldCheck,
  };
}
