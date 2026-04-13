import { type NodeProps } from "@xyflow/react";
import { Timer } from "lucide-react";
import { NodeBase } from "./NodeBase";
import { useI18n } from "@/lib/i18n";
import { getNodeTypeInfo, localize } from "./nodeMeta";
import { getNodeRuntimeProps } from "./runtimeProps";

export function WaitNode({ data, selected }: NodeProps) {
  const { lang } = useI18n();
  const d = data as Record<string, unknown>;
  const minutes = d?.wait_minutes as number | undefined;
  return (
    <NodeBase
      selected={selected}
      label={(d?.label as string) || getNodeTypeInfo("logic/wait", lang).label}
      icon={<Timer className="h-4 w-4 text-purple-400" />}
      description={minutes ? localize(lang, `Пауза на ${minutes} мин.`, `Pause for ${minutes} minute(s)`) : localize(lang, "Настройте длительность паузы", "Configure wait duration")}
      accentColor="border-orange-500/40"
      sourcePorts={[{ id: "done", label: localize(lang, "ГОТОВО", "DONE") }]}
      {...getNodeRuntimeProps(d)}
    />
  );
}
