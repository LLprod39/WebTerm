import { type NodeProps } from "@xyflow/react";
import { NodeBase } from "./NodeBase";
import { useI18n } from "@/lib/i18n";
import { getNodeTypeInfo, localize } from "./nodeMeta";

export function OutputNode({ data, selected, type }: NodeProps) {
  const { lang } = useI18n();
  const meta = getNodeTypeInfo(type as string, lang);
  const d = data as Record<string, string>;
  const url = d?.url;

  return (
    <NodeBase
      selected={selected}
      label={d?.label || meta.label}
      icon={meta.icon}
      description={
        url
          ? url.slice(0, 40)
          : type === "output/report"
            ? localize(lang, "Финальный markdown-отчёт", "Generate markdown report")
            : localize(lang, "Отправка результата в URL", "POST results to URL")
      }
      hasSource={true}
      accentColor="border-rose-500/40"
      status={d?.status}
    />
  );
}
