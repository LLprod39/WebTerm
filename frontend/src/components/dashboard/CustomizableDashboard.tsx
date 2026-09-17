import { useEffect, useMemo, useState, type DragEvent, type MouseEvent } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { cn } from "@/lib/utils";
import {
  fetchDashboardLayout,
  saveDashboardLayout,
  type DashboardLayoutData,
  type DashboardWidgetConfig,
} from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { notify } from "@/lib/notify";

import { DashboardControls, DashboardEditHelp } from "./DashboardControls";
import { DashboardGrid } from "./DashboardGrid";
import { DashboardWidgetPalette } from "./DashboardWidgetPalette";
import {
  getAdjacentDashboardWidth,
  getClosestDashboardWidth,
  getCuratedDefaultDashboardLayout,
  getInitialDashboardLayout,
  getMissingDashboardWidgets,
  getVisibleDashboardWidgets,
  toggleDashboardWidget,
  updateDashboardWidgetProp,
} from "./dashboardLayoutModel";
import type { DashboardType, WidgetDefinition } from "./dashboardTypes";

export type { WidgetDefinition } from "./dashboardTypes";

interface CustomizableDashboardProps {
  type: DashboardType;
  availableWidgets: WidgetDefinition[];
  className?: string;
}

export function CustomizableDashboard({
  type,
  availableWidgets,
  className,
}: CustomizableDashboardProps) {
  const { t } = useI18n();
  const queryClient = useQueryClient();
  const [isEditing, setIsEditing] = useState(false);
  const [localLayout, setLocalLayout] = useState<DashboardWidgetConfig[]>([]);
  const [activeSettingsWidget, setActiveSettingsWidget] = useState<string | null>(null);
  const [draggedIndex, setDraggedIndex] = useState<number | null>(null);

  const { data: layoutResponse, isLoading } = useQuery({
    queryKey: ["dashboard", "layout", type],
    queryFn: () => fetchDashboardLayout(type),
  });

  useEffect(() => {
    if (layoutResponse?.layout?.widgets || availableWidgets.length > 0) {
      setLocalLayout(
        getInitialDashboardLayout({
          availableWidgets,
          savedWidgets: layoutResponse?.layout?.widgets,
          type,
        }),
      );
    }
  }, [availableWidgets, layoutResponse?.layout?.widgets, type]);

  const saveMutation = useMutation({
    mutationFn: (layout: DashboardLayoutData) => saveDashboardLayout(type, layout),
    onSuccess: () => {
      notify.success({ title: t("dash.layout_saved") || "Раскладка успешно сохранена" });
      setIsEditing(false);
      queryClient.invalidateQueries({ queryKey: ["dashboard", "layout", type] });
    },
    onError: (error) => {
      notify.error({ title: t("dash.layout_save_error") || "Ошибка сохранения" });
      console.error(error);
    },
  });

  const visibleWidgets = useMemo(
    () => getVisibleDashboardWidgets(localLayout, availableWidgets),
    [availableWidgets, localLayout],
  );
  const localWidgetIds = useMemo(() => localLayout.map((widget) => widget.id), [localLayout]);

  const handleSave = () => {
    saveMutation.mutate({ widgets: localLayout });
  };

  const handleReset = () => {
    const presets = getCuratedDefaultDashboardLayout(type);
    setLocalLayout(presets.filter((preset) => availableWidgets.some((widget) => widget.id === preset.id)));
    notify.info({ title: "Сброшено к красивой дефолтной раскладке" });
  };

  const addAllWidgets = () => {
    const missingWidgets = getMissingDashboardWidgets(localLayout, availableWidgets);
    if (!missingWidgets.length) {
      notify.info({ title: "Все виджеты уже добавлены" });
      return;
    }
    setLocalLayout((current) => [...current, ...getMissingDashboardWidgets(current, availableWidgets)]);
    notify.success({ title: `Добавлено виджетов: ${missingWidgets.length}` });
  };

  const toggleWidget = (id: string) => {
    setLocalLayout((current) => toggleDashboardWidget(current, availableWidgets, id));
  };

  const updateWidgetProp = (id: string, key: string, value: string | number) => {
    setLocalLayout((current) => updateDashboardWidgetProp(current, id, key, value));
  };

  const handleShrink = (id: string, currentWidth: number) => {
    const nextWidth = getAdjacentDashboardWidth(currentWidth, -1);
    if (nextWidth !== currentWidth) updateWidgetProp(id, "w", nextWidth);
  };

  const handleExpand = (id: string, currentWidth: number) => {
    const nextWidth = getAdjacentDashboardWidth(currentWidth, 1);
    if (nextWidth !== currentWidth) updateWidgetProp(id, "w", nextWidth);
  };

  const handleDragStart = (event: DragEvent<HTMLDivElement>, index: number) => {
    setDraggedIndex(index);
    event.dataTransfer.effectAllowed = "move";
  };

  const handleDragOver = (event: DragEvent<HTMLDivElement>, index: number) => {
    event.preventDefault();
    if (draggedIndex === null || draggedIndex === index) return;

    setLocalLayout((current) => {
      const next = [...current];
      const item = next[draggedIndex];
      next.splice(draggedIndex, 1);
      next.splice(index, 0, item);
      return next;
    });
    setDraggedIndex(index);
  };

  const handleDragEnd = () => {
    setDraggedIndex(null);
  };

  const handleResizeStart = (event: MouseEvent, widgetId: string) => {
    event.preventDefault();
    event.stopPropagation();

    const cardElement = event.currentTarget.closest("[data-widget-id]");
    const gridElement = event.currentTarget.closest(".grid");
    if (!cardElement || !gridElement) return;

    const gridRect = gridElement.getBoundingClientRect();
    const cardRect = cardElement.getBoundingClientRect();
    const cardLeft = cardRect.left - gridRect.left;
    const columnWidth = gridRect.width / 12;

    const handleMouseMove = (moveEvent: globalThis.MouseEvent) => {
      const mouseX = moveEvent.clientX - gridRect.left;
      const desiredWidthPx = mouseX - cardLeft;
      const targetWidth = Math.max(3, Math.min(12, Math.round(desiredWidthPx / columnWidth)));
      updateWidgetProp(widgetId, "w", getClosestDashboardWidth(targetWidth));
    };

    const handleMouseUp = () => {
      window.removeEventListener("mousemove", handleMouseMove);
      window.removeEventListener("mouseup", handleMouseUp);
    };

    window.addEventListener("mousemove", handleMouseMove);
    window.addEventListener("mouseup", handleMouseUp);
  };

  if (isLoading) {
    return <div className="p-8 text-center text-muted-foreground">Загрузка макета дашборда...</div>;
  }

  return (
    <div className={cn("space-y-6", className)}>
      <DashboardControls
        isEditing={isEditing}
        saving={saveMutation.isPending}
        onAddAllWidgets={addAllWidgets}
        onCancelEditing={() => setIsEditing(false)}
        onReset={handleReset}
        onSave={handleSave}
        onStartEditing={() => setIsEditing(true)}
      />
      <DashboardEditHelp isEditing={isEditing} />
      <DashboardWidgetPalette
        availableWidgets={availableWidgets}
        isEditing={isEditing}
        localWidgetIds={localWidgetIds}
        onToggleWidget={toggleWidget}
      />
      <DashboardGrid
        activeSettingsWidget={activeSettingsWidget}
        draggedIndex={draggedIndex}
        isEditing={isEditing}
        visibleWidgets={visibleWidgets}
        onActiveSettingsWidgetChange={setActiveSettingsWidget}
        onDragEnd={handleDragEnd}
        onDragOver={handleDragOver}
        onDragStart={handleDragStart}
        onExpand={handleExpand}
        onResizeStart={handleResizeStart}
        onShrink={handleShrink}
        onStartEditing={() => setIsEditing(true)}
        onToggleWidget={toggleWidget}
        onUpdateWidgetProp={updateWidgetProp}
      />
    </div>
  );
}
