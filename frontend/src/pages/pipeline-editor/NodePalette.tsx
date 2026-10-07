import { useEffect, useMemo, useState, type ComponentType } from "react";
import { ChevronDown, ChevronUp, FileText, PanelLeftClose, PanelLeftOpen, Plus } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { NODE_PALETTE } from "@/components/pipeline/nodes";
import { getNodeCategoryLabel, getNodePaletteText, getNodeTypeGuidance } from "@/components/pipeline/nodes/nodeMeta";
import { cn } from "@/lib/utils";

import { CATEGORY_ICONS, localize } from "./presentation";

type PaletteNode = {
  type: string;
  label: string;
  // Lucide icons and plugin-provided icon components both satisfy this shape.
  icon: ComponentType<{ className?: string }>;
  iconClassName?: string;
  description: string;
};

type PaletteCategory = {
  category: string;
  nodes: PaletteNode[];
};

function paletteText(node: PaletteNode, lang: "en" | "ru") {
  const nodeText = getNodePaletteText(node.type, lang);
  if (nodeText.label === node.type) {
    return { label: node.label, description: node.description };
  }
  return nodeText;
}

export function NodePalette({
  onAddNode,
  lang,
  pluginPalette = [],
  collapsed = false,
  onToggleCollapsed,
}: {
  onAddNode: (type: string) => void;
  lang: "en" | "ru";
  pluginPalette?: PaletteCategory[];
  collapsed?: boolean;
  onToggleCollapsed?: () => void;
}) {
  const [search, setSearch] = useState("");
  const palette = useMemo(
    () => [...(NODE_PALETTE as PaletteCategory[]), ...pluginPalette],
    [pluginPalette],
  );
  const [expandedCats, setExpandedCats] = useState<Set<string>>(new Set(palette.map((c) => c.category)));

  useEffect(() => {
    setExpandedCats((prev) => {
      const next = new Set(prev);
      palette.forEach((category) => next.add(category.category));
      return next;
    });
  }, [palette]);

  const toggleCat = (cat: string) => {
    setExpandedCats((prev) => {
      const next = new Set(prev);
      if (next.has(cat)) next.delete(cat);
      else next.add(cat);
      return next;
    });
  };

  const filtered = palette.map((cat) => ({
    ...cat,
    nodes: cat.nodes.filter((n) => {
      const nodeText = paletteText(n, lang);
      const query = search.trim().toLowerCase();
      return !query || nodeText.label.toLowerCase().includes(query) || nodeText.description.toLowerCase().includes(query);
    }),
  })).filter((cat) => cat.nodes.length > 0);

  const railNodes = useMemo(
    () => palette.flatMap((cat) => cat.nodes),
    [palette],
  );

  if (collapsed) {
    return (
      <div className="flex h-full w-12 flex-col items-center border-r border-border/80 bg-card/95 py-2">
        {onToggleCollapsed ? (
          <TooltipProvider delayDuration={200}>
            <Tooltip>
              <TooltipTrigger asChild>
                <Button
                  type="button"
                  size="icon"
                  variant="ghost"
                  className="mb-2 h-8 w-8"
                  onClick={onToggleCollapsed}
                  aria-label={localize(lang, "Развернуть палитру", "Expand palette")}
                >
                  <PanelLeftOpen className="h-4 w-4" />
                </Button>
              </TooltipTrigger>
              <TooltipContent side="right">
                {localize(lang, "Развернуть палитру", "Expand palette")}
              </TooltipContent>
            </Tooltip>
          </TooltipProvider>
        ) : null}
        <TooltipProvider delayDuration={300}>
          <div className="flex min-h-0 flex-1 flex-col items-center gap-1 overflow-auto px-1 pb-2">
            {railNodes.map((node) => {
              const Icon = node.icon;
              const nodeText = paletteText(node, lang);
              return (
                <Tooltip key={node.type}>
                  <TooltipTrigger asChild>
                    <button
                      type="button"
                      onClick={() => onAddNode(node.type)}
                      draggable
                      onDragStart={(e) => {
                        e.dataTransfer.setData("application/pipeline-node-type", node.type);
                        e.dataTransfer.effectAllowed = "copy";
                      }}
                      className="flex h-8 w-8 items-center justify-center rounded-sm border border-transparent text-muted-foreground transition-colors hover:border-border/70 hover:bg-primary/10 hover:text-foreground cursor-grab active:cursor-grabbing"
                      aria-label={nodeText.label}
                    >
                      <Icon className={cn("h-4 w-4", node.iconClassName || "text-foreground")} />
                    </button>
                  </TooltipTrigger>
                  <TooltipContent side="right" className="max-w-[240px]">
                    <p className="text-xs font-semibold">{nodeText.label}</p>
                    <p className="text-xs text-muted-foreground">{nodeText.description}</p>
                  </TooltipContent>
                </Tooltip>
              );
            })}
          </div>
        </TooltipProvider>
      </div>
    );
  }

  return (
    <div className="flex h-full flex-col border-r border-border/80 bg-card/95">
      <div className="space-y-2 border-b border-border/80 px-3 py-3">
        <div className="flex items-center gap-1.5">
          <h3 className="flex flex-1 items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            <Plus className="h-3 w-3" /> {localize(lang, "Добавить ноду", "Add node")}
          </h3>
          {onToggleCollapsed ? (
            <Button
              type="button"
              size="icon"
              variant="ghost"
              className="h-7 w-7"
              onClick={onToggleCollapsed}
              aria-label={localize(lang, "Свернуть палитру", "Collapse palette")}
            >
              <PanelLeftClose className="h-3.5 w-3.5" />
            </Button>
          ) : null}
        </div>
        <Input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder={localize(lang, "Поиск нод...", "Search nodes...")}
          className="h-8 border-border/70 bg-background/70 text-xs"
        />
      </div>
      <TooltipProvider delayDuration={400}>
        <div className="flex-1 space-y-1 overflow-auto p-2">
          {filtered.map((cat) => {
            const CategoryIcon = CATEGORY_ICONS[cat.category as keyof typeof CATEGORY_ICONS] || FileText;
            return (
              <div key={cat.category}>
                <button
                  onClick={() => toggleCat(cat.category)}
                  className="flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-left text-xs font-semibold uppercase tracking-wide text-muted-foreground transition-colors hover:bg-muted/40 hover:text-foreground"
                >
                  <CategoryIcon className="h-3.5 w-3.5" />
                  <span className="flex-1">{getNodeCategoryLabel(cat.category, lang)}</span>
                  <span className="rounded bg-muted/50 px-1.5 py-0.5 text-xs font-normal">{cat.nodes.length}</span>
                  {expandedCats.has(cat.category) ? (
                    <ChevronUp className="h-3 w-3" />
                  ) : (
                    <ChevronDown className="h-3 w-3" />
                  )}
                </button>
                {expandedCats.has(cat.category) &&
                  cat.nodes.map((node) => {
                    const Icon = node.icon;
                    const guidance = getNodeTypeGuidance(node.type, lang);
                    const nodeText = paletteText(node, lang);
                    return (
                      <Tooltip key={node.type}>
                        <TooltipTrigger asChild>
                          <button
                            onClick={() => onAddNode(node.type)}
                            draggable
                            onDragStart={(e) => {
                              e.dataTransfer.setData("application/pipeline-node-type", node.type);
                              e.dataTransfer.effectAllowed = "copy";
                            }}
                            className="group flex w-full items-center gap-3 rounded-sm border border-transparent px-2.5 py-2.5 text-left transition-all hover:border-border/70 hover:bg-primary/5 cursor-grab active:cursor-grabbing"
                          >
                            <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-sm border border-border/70 bg-muted/40 transition-colors group-hover:border-primary/20 group-hover:bg-primary/10">
                              <Icon className={`h-[18px] w-[18px] ${node.iconClassName || "text-foreground"}`} />
                            </span>
                            <div className="min-w-0 flex-1">
                              <div className="truncate text-[12px] font-medium text-foreground">{nodeText.label}</div>
                              <div className="mt-0.5 truncate text-xs leading-tight text-muted-foreground">{nodeText.description}</div>
                            </div>
                            <Plus className="ml-auto h-3.5 w-3.5 shrink-0 text-primary opacity-0 transition-opacity group-hover:opacity-100" />
                          </button>
                        </TooltipTrigger>
                        <TooltipContent side="right" className="max-w-[320px] rounded-sm border-border/80 bg-popover/98 px-3.5 py-3">
                          <div className="space-y-2">
                            <div className="flex items-start gap-2">
                              <span className="mt-0.5 flex h-8 w-8 items-center justify-center rounded-lg border border-border/70 bg-background/70">
                                <Icon className={`h-4 w-4 ${node.iconClassName || "text-foreground"}`} />
                              </span>
                              <div className="min-w-0">
                                <p className="text-sm font-semibold text-foreground">{nodeText.label}</p>
                                <p className="text-xs uppercase tracking-wide text-muted-foreground">{guidance.category}</p>
                              </div>
                            </div>
                            <p className="text-[12px] leading-5 text-foreground/80">{guidance.summary}</p>
                            <div className="space-y-1">
                              {guidance.checklist.slice(0, 2).map((item) => (
                                <p key={item} className="text-xs leading-4 text-muted-foreground">
                                  - {item}
                                </p>
                              ))}
                            </div>
                          </div>
                        </TooltipContent>
                      </Tooltip>
                    );
                  })}
              </div>
            );
          })}
          {filtered.length === 0 && search.trim() && (
            <p className="py-4 text-center text-xs text-muted-foreground">
              {localize(lang, `Ничего не найдено по запросу "${search}"`, `No nodes match "${search}"`)}
            </p>
          )}
        </div>
      </TooltipProvider>
      <div className="border-t border-border/80 px-3 py-2">
        <p className="text-center text-xs text-muted-foreground">
          {localize(lang, "Кликните по ноде или перетащите её на холст", "Click a node or drag it onto the canvas")}
        </p>
      </div>
    </div>
  );
}
