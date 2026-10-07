import { type ReactNode } from "react";
import { type NodeProps } from "@xyflow/react";
import {
  Archive,
  BellDot,
  Container,
  FileCode2,
  Globe2,
  HardDrive,
  Package,
  ScrollText,
  ServerCog,
  Settings2,
  Zap,
} from "lucide-react";
import { NodeBase } from "./NodeBase";
import { useI18n } from "@/lib/i18n";
import { getNodeBranchLabel, getNodePaletteText } from "./nodeMeta";
import { getNodeRuntimeProps } from "./runtimeProps";

const OPS_ICONS: Record<string, ReactNode> = {
  "ops/server_snapshot": <ServerCog className="h-4 w-4 text-info" />,
  "ops/log_query": <ScrollText className="h-4 w-4 text-success" />,
  "ops/file_action": <FileCode2 className="h-4 w-4 text-warning" />,
  "ops/package_action": <Package className="h-4 w-4 text-warning" />,
  "ops/disk_cleanup": <HardDrive className="h-4 w-4 text-destructive" />,
  "ops/backup_restore_check": <Archive className="h-4 w-4 text-success" />,
  "ops/service_action": <Settings2 className="h-4 w-4 text-warning" />,
  "ops/docker_action": <Container className="h-4 w-4 text-info" />,
  "ops/process_action": <Zap className="h-4 w-4 text-destructive" />,
  "ops/http_check": <Globe2 className="h-4 w-4 text-success" />,
  "ops/alert_update": <BellDot className="h-4 w-4 text-warning" />,
};

export function OpsNode({ data, selected, type }: NodeProps) {
  const { lang } = useI18n();
  const palette = getNodePaletteText(type as string, lang);
  const d = data as Record<string, unknown>;

  return (
    <NodeBase
      selected={selected}
      label={(typeof d?.label === "string" ? d.label : "") || palette.label}
      icon={OPS_ICONS[type as string] ?? <ServerCog className="h-4 w-4 text-info" />}
      description={palette.description}
      sourcePorts={[
        { id: "success", label: getNodeBranchLabel("success", lang), className: "!bg-success/70 hover:!bg-success", labelClassName: "text-success" },
        { id: "error", label: getNodeBranchLabel("error", lang), className: "!bg-destructive/70 hover:!bg-destructive", labelClassName: "text-destructive" },
      ]}
      accentColor="border-info/40"
      categoryColor="hsl(var(--info))"
      {...getNodeRuntimeProps(d)}
    />
  );
}
