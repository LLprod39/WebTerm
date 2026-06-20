import type { DragEvent, MouseEvent } from "react";
import { motion } from "framer-motion";
import { GripVertical, Layout, Minus, Plus, SlidersHorizontal, Trash2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

import {
  dashboardColSpanClasses,
  DASHBOARD_WIDGET_WIDTHS,
  dashboardLimitedListWidgetIds,
  getDashboardWidthLabel,
} from "./dashboardLayoutModel";
import { getWidgetNumberProp, getWidgetStringProp } from "./widgetProps";
import type { VisibleDashboardWidget } from "./dashboardTypes";

export function DashboardGrid({
  activeSettingsWidget,
  draggedIndex,
  isEditing,
  onActiveSettingsWidgetChange,
  onDragEnd,
  onDragOver,
  onDragStart,
  onExpand,
  onResizeStart,
  onShrink,
  onStartEditing,
  onToggleWidget,
  onUpdateWidgetProp,
  visibleWidgets,
}: {
  activeSettingsWidget: string | null;
  draggedIndex: number | null;
  isEditing: boolean;
  onActiveSettingsWidgetChange: (widgetId: string | null) => void;
  onDragEnd: () => void;
  onDragOver: (event: DragEvent<HTMLDivElement>, index: number) => void;
  onDragStart: (event: DragEvent<HTMLDivElement>, index: number) => void;
  onExpand: (id: string, currentWidth: number) => void;
  onResizeStart: (event: MouseEvent, widgetId: string, currentWidth: number) => void;
  onShrink: (id: string, currentWidth: number) => void;
  onStartEditing: () => void;
  onToggleWidget: (id: string) => void;
  onUpdateWidgetProp: (id: string, key: string, value: string | number) => void;
  visibleWidgets: VisibleDashboardWidget[];
}) {
  return (
    <div className="grid grid-cols-12 gap-4 relative">
      {isEditing ? <DashboardGridLines /> : null}

      {visibleWidgets.map((item, index) => (
        <DashboardWidgetFrame
          key={item.config.id}
          activeSettingsWidget={activeSettingsWidget}
          index={index}
          isEditing={isEditing}
          isWidgetDragged={draggedIndex === index}
          item={item}
          onActiveSettingsWidgetChange={onActiveSettingsWidgetChange}
          onDragEnd={onDragEnd}
          onDragOver={onDragOver}
          onDragStart={onDragStart}
          onExpand={onExpand}
          onResizeStart={onResizeStart}
          onShrink={onShrink}
          onToggleWidget={onToggleWidget}
          onUpdateWidgetProp={onUpdateWidgetProp}
        />
      ))}

      {visibleWidgets.length === 0 ? <EmptyDashboardState onStartEditing={onStartEditing} /> : null}
    </div>
  );
}

function DashboardGridLines() {
  return (
    <div className="absolute inset-0 grid grid-cols-12 gap-4 pointer-events-none opacity-[0.025] px-0 z-0">
      {Array.from({ length: 12 }).map((_, index) => (
        <div key={index} className="h-full border-x border-dashed border-primary bg-primary/10 rounded-sm" />
      ))}
    </div>
  );
}

function DashboardWidgetFrame({
  activeSettingsWidget,
  index,
  isEditing,
  isWidgetDragged,
  item,
  onActiveSettingsWidgetChange,
  onDragEnd,
  onDragOver,
  onDragStart,
  onExpand,
  onResizeStart,
  onShrink,
  onToggleWidget,
  onUpdateWidgetProp,
}: {
  activeSettingsWidget: string | null;
  index: number;
  isEditing: boolean;
  isWidgetDragged: boolean;
  item: VisibleDashboardWidget;
  onActiveSettingsWidgetChange: (widgetId: string | null) => void;
  onDragEnd: () => void;
  onDragOver: (event: DragEvent<HTMLDivElement>, index: number) => void;
  onDragStart: (event: DragEvent<HTMLDivElement>, index: number) => void;
  onExpand: (id: string, currentWidth: number) => void;
  onResizeStart: (event: MouseEvent, widgetId: string, currentWidth: number) => void;
  onShrink: (id: string, currentWidth: number) => void;
  onToggleWidget: (id: string) => void;
  onUpdateWidgetProp: (id: string, key: string, value: string | number) => void;
}) {
  const width = item.config.w ?? item.def.defaultSize.w ?? 12;
  const hasSettings = activeSettingsWidget === item.config.id;
  const gridClass = dashboardColSpanClasses[width] || "col-span-12";

  return (
    <motion.div
      layout
      data-widget-id={item.config.id}
      transition={{ type: "spring", stiffness: 450, damping: 38 }}
      onDragOver={(event) => onDragOver(event, index)}
      className={cn(
        "relative transition-all duration-300 rounded-xl z-10",
        gridClass,
        isEditing && "group ring-1 ring-border/30 hover:ring-primary/40 bg-secondary/5 border border-dashed border-border/50 p-1",
        isWidgetDragged && "opacity-35 ring-2 ring-primary border-primary shadow-xl z-30",
      )}
    >
      {isEditing ? (
        <DashboardWidgetEditHeader
          hasSettings={hasSettings}
          item={item}
          onActiveSettingsWidgetChange={onActiveSettingsWidgetChange}
          onDragEnd={onDragEnd}
          onDragStart={(event) => onDragStart(event, index)}
          onExpand={onExpand}
          onShrink={onShrink}
          onToggleWidget={onToggleWidget}
          width={width}
        />
      ) : null}

      {isEditing && hasSettings ? (
        <DashboardWidgetSettings item={item} onUpdateWidgetProp={onUpdateWidgetProp} width={width} />
      ) : null}

      <div className={cn(isEditing && "pointer-events-none opacity-90 transition-all relative")}>
        {item.def.render(item.config)}
        {isEditing ? <div className="absolute inset-0 bg-background/5 border border-primary/5 rounded-xl pointer-events-none" /> : null}
      </div>

      {isEditing ? (
        <DashboardResizeHandle
          onResizeStart={(event) => onResizeStart(event, item.config.id, width)}
        />
      ) : null}
    </motion.div>
  );
}

function DashboardWidgetEditHeader({
  hasSettings,
  item,
  onActiveSettingsWidgetChange,
  onDragEnd,
  onDragStart,
  onExpand,
  onShrink,
  onToggleWidget,
  width,
}: {
  hasSettings: boolean;
  item: VisibleDashboardWidget;
  onActiveSettingsWidgetChange: (widgetId: string | null) => void;
  onDragEnd: () => void;
  onDragStart: (event: DragEvent<HTMLDivElement>) => void;
  onExpand: (id: string, currentWidth: number) => void;
  onShrink: (id: string, currentWidth: number) => void;
  onToggleWidget: (id: string) => void;
  width: number;
}) {
  return (
    <div
      draggable
      onDragStart={onDragStart}
      onDragEnd={onDragEnd}
      className="relative mb-2 flex items-center justify-between gap-2 rounded-lg bg-card/95 px-3 py-2 border border-border shadow-sm text-xs backdrop-blur-sm z-10 cursor-grab active:cursor-grabbing hover:border-primary/50 hover:bg-secondary/40 transition-all select-none"
      title="Зажмите и тащите для перемещения"
    >
      <div className="flex items-center gap-2 min-w-0">
        <GripVertical className="h-4 w-4 text-primary/70 shrink-0" />
        <span className="font-bold truncate text-foreground select-none">
          {getWidgetStringProp(item.config, "customTitle", item.def.title)}
        </span>
        <span className="text-[9px] text-muted-foreground bg-secondary px-1.5 py-0.5 rounded font-mono shrink-0 select-none">
          {getDashboardWidthLabel(width)}
        </span>
      </div>

      <div className="flex items-center gap-1 shrink-0" onClick={(event) => event.stopPropagation()} draggable={false}>
        <Button
          variant="ghost"
          size="icon"
          onClick={() => onShrink(item.config.id, width)}
          disabled={width === 3}
          className="h-6 w-6 rounded-md text-muted-foreground hover:bg-secondary disabled:opacity-40"
          title="Уменьшить ширину"
        >
          <Minus className="h-3.5 w-3.5" />
        </Button>
        <Button
          variant="ghost"
          size="icon"
          onClick={() => onExpand(item.config.id, width)}
          disabled={width === 12}
          className="h-6 w-6 rounded-md text-muted-foreground hover:bg-secondary disabled:opacity-40"
          title="Увеличить ширину"
        >
          <Plus className="h-3.5 w-3.5" />
        </Button>
        <div className="w-px h-3.5 bg-border mx-0.5" />
        <Button
          variant={hasSettings ? "default" : "ghost"}
          size="icon"
          onClick={() => onActiveSettingsWidgetChange(hasSettings ? null : item.config.id)}
          className={cn("h-6 w-6 rounded-md text-muted-foreground", hasSettings && "text-primary-foreground")}
          title="Настройки параметров виджета"
        >
          <SlidersHorizontal className="h-3.5 w-3.5" />
        </Button>
        <div className="w-px h-3.5 bg-border mx-0.5" />
        <Button
          variant="ghost"
          size="icon"
          onClick={() => onToggleWidget(item.config.id)}
          className="h-6 w-6 rounded-md hover:bg-destructive/10 text-muted-foreground hover:text-destructive"
          title="Убрать с дашборда"
        >
          <Trash2 className="h-3.5 w-3.5" />
        </Button>
      </div>
    </div>
  );
}

function DashboardWidgetSettings({
  item,
  onUpdateWidgetProp,
  width,
}: {
  item: VisibleDashboardWidget;
  onUpdateWidgetProp: (id: string, key: string, value: string | number) => void;
  width: number;
}) {
  return (
    <motion.div
      initial={{ opacity: 0, y: -5 }}
      animate={{ opacity: 1, y: 0 }}
      className="mb-3 rounded-lg border border-primary/20 bg-primary/5 p-3 text-xs space-y-3 shadow-inner"
    >
      <div className="font-semibold text-foreground flex items-center gap-1">
        <SlidersHorizontal className="h-3.5 w-3.5 text-primary" /> Параметры: {item.def.title}
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
        <div className="space-y-1">
          <label className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground block">Предустановка ширины</label>
          <div className="flex flex-wrap gap-1">
            {DASHBOARD_WIDGET_WIDTHS.map((size) => (
              <button
                key={size}
                type="button"
                onClick={() => onUpdateWidgetProp(item.config.id, "w", size)}
                className={cn(
                  "px-2 py-1 rounded text-[10px] font-semibold border transition-all",
                  width === size
                    ? "bg-primary text-primary-foreground border-primary shadow-sm"
                    : "bg-background/80 hover:bg-secondary border-border text-foreground",
                )}
              >
                {getDashboardWidthLabel(size)}
              </button>
            ))}
          </div>
        </div>

        <div className="space-y-1">
          <label className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground block">Свой заголовок</label>
          <input
            type="text"
            placeholder={item.def.title}
            value={getWidgetStringProp(item.config, "customTitle", "")}
            onChange={(event) => onUpdateWidgetProp(item.config.id, "customTitle", event.target.value)}
            className="w-full h-8 px-2.5 rounded-md border border-border bg-background hover:border-accent focus:border-primary transition-all text-xs"
          />
        </div>

        <div className="space-y-1">
          <label className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground block">Визуальная схема (тон)</label>
          <select
            value={getWidgetStringProp(item.config, "tone", "default")}
            onChange={(event) => onUpdateWidgetProp(item.config.id, "tone", event.target.value)}
            className="w-full h-8 px-2 rounded-md border border-border bg-background text-xs cursor-pointer focus:border-primary"
          >
            <option value="default">По умолчанию</option>
            <option value="info">Инфо (Синий)</option>
            <option value="success">Успех (Зеленый)</option>
            <option value="warning">Внимание (Оранжевый)</option>
            <option value="danger">Критический (Красный)</option>
          </select>
        </div>

        {dashboardLimitedListWidgetIds.has(item.config.id) ? (
          <div className="space-y-1">
            <label className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground block">Лимит строк / объектов</label>
            <select
              value={getWidgetNumberProp(item.config, "limit", 5)}
              onChange={(event) => onUpdateWidgetProp(item.config.id, "limit", parseInt(event.target.value))}
              className="w-full h-8 px-2 rounded-md border border-border bg-background text-xs cursor-pointer focus:border-primary"
            >
              {[3, 5, 8, 10, 15, 20].map((limit) => (
                <option key={limit} value={limit}>{limit} элементов</option>
              ))}
            </select>
          </div>
        ) : null}
      </div>
    </motion.div>
  );
}

function DashboardResizeHandle({ onResizeStart }: { onResizeStart: (event: MouseEvent) => void }) {
  return (
    <div
      className="absolute right-0 top-0 bottom-0 w-3.5 cursor-col-resize hover:bg-primary/5 active:bg-primary/10 transition-colors z-20 flex items-center justify-end group select-none"
      onMouseDown={onResizeStart}
      title="Потяните за край для изменения ширины"
    >
      <div className="absolute right-0 top-0 bottom-0 w-1 bg-border/40 group-hover:bg-primary/60 group-active:bg-primary transition-all" />
      <div className="mr-0.5 w-1.5 h-12 rounded-full bg-muted-foreground/35 group-hover:bg-primary group-active:bg-primary transition-all shadow-sm flex flex-col gap-0.5 items-center justify-center opacity-0 group-hover:opacity-100 duration-200">
        <span className="w-0.5 h-0.5 rounded-full bg-primary-foreground" />
        <span className="w-0.5 h-0.5 rounded-full bg-primary-foreground" />
        <span className="w-0.5 h-0.5 rounded-full bg-primary-foreground" />
      </div>
    </div>
  );
}

function EmptyDashboardState({ onStartEditing }: { onStartEditing: () => void }) {
  return (
    <div className="col-span-12 py-16 text-center border-2 border-dashed rounded-2xl border-border bg-card/30 backdrop-blur-md">
      <Layout className="h-10 w-10 text-muted-foreground/40 mx-auto mb-3" />
      <h3 className="font-semibold text-foreground/80 mb-1">Дашборд пуст</h3>
      <p className="text-xs text-muted-foreground max-w-sm mx-auto mb-4">
        Нажмите кнопку "Настроить виджеты", чтобы добавить информационные панели на экран.
      </p>
      <Button variant="outline" size="sm" onClick={onStartEditing}>
        Начать настройку
      </Button>
    </div>
  );
}
