import { type NodeProps } from "@xyflow/react";
import { NodeBase } from "./NodeBase";
import { useI18n } from "@/lib/i18n";
import { getNodeTypeInfo, localize } from "./nodeMeta";

export function WaitNode({ data, selected }: NodeProps) {
  const { lang } = useI18n();
  const d = data as Record<string, unknown>;
  const minutes = d?.wait_minutes as number | undefined;
  return (
    <NodeBase
      selected={selected}
      label={(d?.label as string) || getNodeTypeInfo("logic/wait", lang).label}
      icon="⏱️"
      description={minutes ? localize(lang, `Пауза на ${minutes} мин.`, `Pause for ${minutes} minute(s)`) : localize(lang, "Настройте длительность паузы", "Configure wait duration")}
      accentColor="border-orange-500/40"
      status={d?.status as string | undefined}
    />
  );
}
