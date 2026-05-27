import { type NodeProps } from "@xyflow/react";
import { FileText, ExternalLink } from "lucide-react";
import { NodeBase } from "./NodeBase";
import { useI18n } from "@/lib/i18n";
import { getNodeBranchLabel, getNodeTypeInfo, localize } from "./nodeMeta";
import { getNodeRuntimeProps } from "./runtimeProps";

export function OutputNode({ data, selected, type }: NodeProps) {
  const { lang } = useI18n();
  const meta = getNodeTypeInfo(type as string, lang);
  const d = data as Record<string, unknown>;
  const url = typeof d?.url === "string" ? d.url : "";

  return (
    <NodeBase
      selected={selected}
      label={(typeof d?.label === "string" ? d.label : "") || meta.label}
      icon={type === "output/report"
        ? <FileText      className="h-4 w-4 text-emerald-400" />
        : <ExternalLink  className="h-4 w-4 text-emerald-400" />}
      description={
        url
          ? url.slice(0, 40)
          : type === "output/report"
            ? localize(lang, "Финальный markdown-отчёт", "Generate markdown report")
            : localize(lang, "Отправка результата в URL", "POST results to URL")
      }
      sourcePorts={[
        { id: "success", label: getNodeBranchLabel("success", lang), className: "!bg-green-500/70 hover:!bg-green-500", labelClassName: "text-green-500" },
        { id: "error", label: getNodeBranchLabel("error", lang), className: "!bg-red-500/70 hover:!bg-red-500", labelClassName: "text-red-500" },
      ]}
      accentColor="border-rose-500/40"
      categoryColor="#34d399"
      {...getNodeRuntimeProps(d)}
    />
  );
}
