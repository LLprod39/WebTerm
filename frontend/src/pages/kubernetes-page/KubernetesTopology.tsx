/**
 * Lightweight topology: namespaces → workloads → services (client-side from inventory).
 */
import { useMemo, useState } from "react";
import type { KubernetesNetworkRef, KubernetesNamespaceSummary, KubernetesWorkloadRef } from "@/api";
import { localize } from "@/lib/i18n";
import { CockpitChip } from "@/pages/kubernetes-page/KubernetesCockpitPrimitives";

type NodeKind = "namespace" | "workload" | "service";

type TopoNode = {
  id: string;
  kind: NodeKind;
  label: string;
  sub?: string;
  health?: string;
  x: number;
  y: number;
};

type TopoEdge = { from: string; to: string };

function healthStroke(health?: string) {
  if (health === "healthy") return "#34d399";
  if (health === "warning") return "#fbbf24";
  if (health === "degraded") return "#f87171";
  return "hsl(var(--border-strong))";
}

export function KubernetesTopology({
  lang,
  namespaces,
  workloads,
  networkRefs,
}: {
  lang: string;
  namespaces: KubernetesNamespaceSummary[];
  workloads: KubernetesWorkloadRef[];
  networkRefs: KubernetesNetworkRef[];
}) {
  const [focusNs, setFocusNs] = useState<string>("");

  const nsNames = useMemo(() => {
    const set = new Set<string>();
    namespaces.forEach((n) => set.add(n.name));
    workloads.forEach((w) => set.add(w.namespace));
    networkRefs.forEach((n) => set.add(n.namespace));
    return Array.from(set).filter(Boolean).sort().slice(0, 12);
  }, [namespaces, workloads, networkRefs]);

  const activeNs = focusNs || nsNames[0] || "";

  const graph = useMemo(() => {
    const wInNs = workloads.filter((w) => w.namespace === activeNs).slice(0, 8);
    const sInNs = networkRefs.filter((n) => n.namespace === activeNs && n.kind === "service").slice(0, 8);
    const nodes: TopoNode[] = [];
    const edges: TopoEdge[] = [];
    const width = 640;
    const height = 280;

    nodes.push({
      id: `ns:${activeNs}`,
      kind: "namespace",
      label: activeNs || "namespace",
      sub: localize(lang, "namespace", "namespace"),
      x: 48,
      y: height / 2,
    });

    wInNs.forEach((w, i) => {
      const id = `wl:${w.id}`;
      const y = 36 + (i * (height - 72)) / Math.max(1, wInNs.length - 1 || 1);
      nodes.push({
        id,
        kind: "workload",
        label: w.name,
        sub: w.kind,
        health: w.health,
        x: width * 0.42,
        y: wInNs.length === 1 ? height / 2 : y,
      });
      edges.push({ from: `ns:${activeNs}`, to: id });
    });

    sInNs.forEach((s, i) => {
      const id = `svc:${s.id}`;
      const y = 36 + (i * (height - 72)) / Math.max(1, sInNs.length - 1 || 1);
      nodes.push({
        id,
        kind: "service",
        label: s.name,
        sub: s.service_type || "Service",
        health: s.health,
        x: width * 0.82,
        y: sInNs.length === 1 ? height / 2 : y,
      });
      // Heuristic: link services to workloads with same prefix/name stem
      const stem = s.name.replace(/-svc$|-service$/i, "");
      const match = wInNs.find((w) => w.name.includes(stem) || stem.includes(w.name));
      if (match) edges.push({ from: `wl:${match.id}`, to: id });
      else if (wInNs[0]) edges.push({ from: `wl:${wInNs[0].id}`, to: id });
    });

    return { nodes, edges, width, height };
  }, [activeNs, workloads, networkRefs, lang]);

  if (!nsNames.length) {
    return (
      <div className="rounded-sm border border-dashed border-border px-4 py-8 text-center text-xs text-muted-foreground">
        {localize(lang, "Нет данных для topology — синхронизируйте inventory.", "No topology data — sync inventory first.")}
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap gap-1.5">
        {nsNames.map((ns) => (
          <CockpitChip key={ns} active={ns === activeNs} onClick={() => setFocusNs(ns)}>
            {ns}
          </CockpitChip>
        ))}
      </div>
      <div className="overflow-x-auto rounded-sm border border-border bg-surface-0 p-2 shadow-elev-1">
        <svg
          viewBox={`0 0 ${graph.width} ${graph.height}`}
          className="h-[280px] w-full min-w-[520px]"
          role="img"
          aria-label="Kubernetes topology"
        >
          {graph.edges.map((e) => {
            const a = graph.nodes.find((n) => n.id === e.from);
            const b = graph.nodes.find((n) => n.id === e.to);
            if (!a || !b) return null;
            return (
              <line
                key={`${e.from}-${e.to}`}
                x1={a.x + 56}
                y1={a.y}
                x2={b.x - 56}
                y2={b.y}
                stroke="hsl(var(--border-strong))"
                strokeWidth="1.25"
                strokeDasharray="4 3"
              />
            );
          })}
          {graph.nodes.map((n) => (
            <g key={n.id} transform={`translate(${n.x - 56}, ${n.y - 22})`}>
              <rect
                width="112"
                height="44"
                rx="2"
                fill="hsl(var(--card))"
                stroke={healthStroke(n.health)}
                strokeWidth={n.kind === "namespace" ? 2 : 1.25}
              />
              <text x="8" y="18" className="fill-foreground" style={{ fontSize: 11, fontWeight: 600 }}>
                {n.label.length > 14 ? `${n.label.slice(0, 13)}…` : n.label}
              </text>
              <text x="8" y="34" className="fill-muted-foreground" style={{ fontSize: 9 }}>
                {n.sub}
              </text>
            </g>
          ))}
        </svg>
      </div>
      <p className="text-2xs text-muted-foreground">
        {localize(
          lang,
          "Эвристика связей service↔workload по имени. Для live graph — Admin Mode.",
          "Service↔workload links are name heuristics. Use Admin Mode for live graph.",
        )}
      </p>
    </div>
  );
}
