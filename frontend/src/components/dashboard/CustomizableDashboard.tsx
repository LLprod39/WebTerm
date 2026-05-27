import { useState, useEffect, ReactNode, DragEvent } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { motion, AnimatePresence } from "framer-motion";
import { 
  Layout, Save, X, Plus, Settings2, RotateCcw, 
  Trash2, SlidersHorizontal, GripVertical, Info,
  Minus, HelpCircle
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import {
  fetchDashboardLayout,
  saveDashboardLayout,
  type DashboardLayoutData,
  type DashboardWidgetConfig,
} from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { toast } from "sonner";

export interface WidgetDefinition {
  id: string;
  title: string;
  icon?: ReactNode;
  defaultSize: { w: number; h: number };
  render: (config: DashboardWidgetConfig) => ReactNode;
}

interface CustomizableDashboardProps {
  type: "admin" | "user";
  availableWidgets: WidgetDefinition[];
  className?: string;
}

const colSpanClasses: Record<number, string> = {
  3: "col-span-12 md:col-span-3 lg:col-span-3",
  4: "col-span-12 md:col-span-4 lg:col-span-4",
  6: "col-span-12 md:col-span-6 lg:col-span-6",
  8: "col-span-12 md:col-span-8 lg:col-span-8",
  9: "col-span-12 md:col-span-9 lg:col-span-9",
  12: "col-span-12",
};

const widgetDescriptions: Record<string, string> = {
  // User widgets
  quick_stats: "Краткая сводка с ключевыми метриками ваших серверов, активных агентов и алертов.",
  servers_health: "Состояние и загрузка CPU/RAM серверов во флоте с быстрыми ссылками на терминал.",
  quick_tools: "Панель быстрых действий для мгновенного перехода в Хаб серверов, Студию или Настройки.",
  active_runs: "Список запущенных в данный момент агентов с отслеживанием статуса.",
  recent_runs: "История последних завершенных запусков AI-агентов с метриками и временем.",
  user_alerts: "Список последних активных предупреждений и критических алертов по серверам.",
  recent_activity: "Лог ваших последних действий в системе с временными метками.",
  recent_servers: "Быстрый доступ к вашим недавно подключенным серверам и их терминалам.",
  
  // Admin widgets
  fleet_metrics: "Инфраструктурные метрики: общее число серверов, средняя нагрузка флота и алерты.",
  hourly_activity_chart: "Интерактивный график активности системы за последние 24 часа.",
  ai_cost_tokens: "Анализ затрат на LLM, количество токенов и ошибок по каждому провайдеру.",
  active_providers: "Статус доступности и активные модели ИИ-провайдеров.",
  online_users: "Список пользователей, находящихся сейчас в системе, и их действия.",
  top_users: "Рейтинг наиболее активных пользователей по операциям и запросам ИИ.",
  active_terminals: "Список активных в данный момент SSH/RDP терминальных сессий.",
  system_alerts_list: "Критические инфраструктурные алерты, требующие внимания администратора."
};

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

  // 1. Fetch saved layout
  const { data: layoutResponse, isLoading } = useQuery({
    queryKey: ["dashboard", "layout", type],
    queryFn: () => fetchDashboardLayout(type),
  });

  // Helper to load curated default layout presets
  const getCuratedDefaultLayout = (): DashboardWidgetConfig[] => {
    if (type === "user") {
      return [
        { id: "quick_stats", x: 0, y: 0, w: 12, h: 1, props: { tone: "default", limit: 5 } },
        { id: "servers_health", x: 0, y: 1, w: 8, h: 1, props: { tone: "default", limit: 5 } },
        { id: "quick_tools", x: 8, y: 1, w: 4, h: 1, props: { tone: "default", limit: 5 } },
        { id: "active_runs", x: 0, y: 2, w: 6, h: 1, props: { tone: "default", limit: 5 } },
        { id: "recent_runs", x: 6, y: 2, w: 6, h: 1, props: { tone: "default", limit: 5 } },
        { id: "user_alerts", x: 0, y: 3, w: 6, h: 1, props: { tone: "default", limit: 5 } },
        { id: "recent_activity", x: 6, y: 3, w: 6, h: 1, props: { tone: "default", limit: 5 } }
      ];
    } else { // admin
      return [
        { id: "fleet_metrics", x: 0, y: 0, w: 12, h: 1, props: { tone: "default", limit: 5 } },
        { id: "hourly_activity_chart", x: 0, y: 1, w: 8, h: 1, props: { tone: "default", limit: 5 } },
        { id: "active_providers", x: 8, y: 1, w: 4, h: 1, props: { tone: "default", limit: 5 } },
        { id: "top_users", x: 0, y: 2, w: 6, h: 1, props: { tone: "default", limit: 5 } },
        { id: "online_users", x: 6, y: 2, w: 6, h: 1, props: { tone: "default", limit: 5 } },
        { id: "ai_cost_tokens", x: 0, y: 3, w: 8, h: 1, props: { tone: "default", limit: 5 } },
        { id: "active_terminals", x: 8, y: 3, w: 4, h: 1, props: { tone: "default", limit: 5 } },
        { id: "system_alerts_list", x: 0, y: 4, w: 6, h: 1, props: { tone: "default", limit: 5 } },
        { id: "recent_activity", x: 6, y: 4, w: 6, h: 1, props: { tone: "default", limit: 5 } }
      ];
    }
  };

  // 2. Initialize local layout
  useEffect(() => {
    if (layoutResponse?.layout?.widgets) {
      const validatedWidgets = layoutResponse.layout.widgets.map(lc => {
        const def = availableWidgets.find(w => w.id === lc.id);
        return {
          ...lc,
          w: lc.w && [3, 4, 6, 8, 9, 12].includes(lc.w) ? lc.w : (def?.defaultSize.w || 12)
        };
      });
      setLocalLayout(validatedWidgets);
    } else if (availableWidgets.length > 0) {
      const presets = getCuratedDefaultLayout();
      const filtered = presets.filter(p => availableWidgets.some(w => w.id === p.id));
      
      // Fallback: If filtered is empty, load all available widgets
      if (filtered.length === 0) {
        const fallbackLayout = availableWidgets.map((w, idx) => ({
          id: w.id,
          x: 0,
          y: idx,
          w: w.defaultSize.w || 12,
          h: 1,
          props: { tone: "default", limit: 5 }
        }));
        setLocalLayout(fallbackLayout);
      } else {
        setLocalLayout(filtered);
      }
    }
  }, [layoutResponse, availableWidgets, type]);

  // 3. Mutation to save
  const saveMutation = useMutation({
    mutationFn: (layout: DashboardLayoutData) => saveDashboardLayout(type, layout),
    onSuccess: () => {
      toast.success(t("dash.layout_saved") || "Раскладка успешно сохранена");
      setIsEditing(false);
      queryClient.invalidateQueries({ queryKey: ["dashboard", "layout", type] });
    },
    onError: (err) => {
      toast.error(t("dash.layout_save_error") || "Ошибка сохранения");
      console.error(err);
    },
  });

  const handleSave = () => {
    saveMutation.mutate({ widgets: localLayout });
  };

  const handleReset = () => {
    const presets = getCuratedDefaultLayout();
    const filtered = presets.filter(p => availableWidgets.some(w => w.id === p.id));
    setLocalLayout(filtered);
    toast.info("Сброшено к красивой дефолтной раскладке");
  };

  const addAllWidgets = () => {
    const currentIds = localLayout.map(w => w.id);
    const missingWidgets = availableWidgets.filter(w => !currentIds.includes(w.id));
    
    if (missingWidgets.length === 0) {
      toast.info("Все виджеты уже добавлены");
      return;
    }

    setLocalLayout((prev) => [
      ...prev,
      ...missingWidgets.map((w, idx) => ({
        id: w.id,
        x: 0,
        y: prev.length + idx,
        w: w.defaultSize.w || 12,
        h: 1,
        props: {
          tone: "default",
          limit: 5,
        }
      }))
    ]);
    toast.success(`Добавлено виджетов: ${missingWidgets.length}`);
  };

  const toggleWidget = (id: string) => {
    setLocalLayout((prev) => {
      const exists = prev.find((w) => w.id === id);
      if (exists) {
        return prev.filter((w) => w.id !== id);
      } else {
        const def = availableWidgets.find((w) => w.id === id);
        return [
          ...prev, 
          { 
            id, 
            x: 0, 
            y: prev.length, 
            w: def?.defaultSize.w || 12, 
            h: 1,
            props: {
              tone: "default",
              limit: 5,
            }
          }
        ];
      }
    });
  };

  const updateWidgetProp = (id: string, key: string, value: any) => {
    setLocalLayout((prev) =>
      prev.map((widget) => {
        if (widget.id !== id) return widget;
        
        if (key === "w") {
          return { ...widget, w: value };
        }
        
        const currentProps = widget.props ?? {};
        return {
          ...widget,
          props: {
            ...currentProps,
            [key]: value,
          },
        };
      })
    );
  };

  // --- SQUEEZE & STRETCH CONTROLS (+ / -) ---
  const handleShrink = (id: string, currentW: number) => {
    const possibleWidths = [3, 4, 6, 8, 9, 12];
    const currentIndex = possibleWidths.indexOf(currentW);
    if (currentIndex > 0) {
      updateWidgetProp(id, "w", possibleWidths[currentIndex - 1]);
    }
  };

  const handleExpand = (id: string, currentW: number) => {
    const possibleWidths = [3, 4, 6, 8, 9, 12];
    const currentIndex = possibleWidths.indexOf(currentW);
    if (currentIndex < possibleWidths.length - 1) {
      updateWidgetProp(id, "w", possibleWidths[currentIndex + 1]);
    }
  };

  // --- MOUSE-DRAG REORDER (HTML5 DnD with Clean Fluid Splicing) ---
  const handleDragStart = (e: DragEvent<HTMLDivElement>, index: number) => {
    setDraggedIndex(index);
    e.dataTransfer.effectAllowed = "move";
  };

  const handleDragOver = (e: DragEvent<HTMLDivElement>, index: number) => {
    e.preventDefault();
    if (draggedIndex === null || draggedIndex === index) return;
    
    // Smooth fluid slicing instead of instant jumpy swapping!
    const fromIndex = draggedIndex;
    const toIndex = index;
    
    setLocalLayout((prev) => {
      const next = [...prev];
      const item = next[fromIndex];
      next.splice(fromIndex, 1);
      next.splice(toIndex, 0, item);
      return next;
    });
    setDraggedIndex(toIndex);
  };

  const handleDragEnd = () => {
    setDraggedIndex(null);
  };

  // --- MATHEMATICALLY PERFECT RESIZE (Edge Dragging Relative to Grid) ---
  const handleResizeStart = (e: React.MouseEvent, widgetId: string, currentW: number) => {
    e.preventDefault();
    e.stopPropagation();
    
    const cardEl = e.currentTarget.closest("[data-widget-id]");
    const gridEl = e.currentTarget.closest(".grid");
    if (!cardEl || !gridEl) return;
    
    const gridRect = gridEl.getBoundingClientRect();
    const cardRect = cardEl.getBoundingClientRect();
    
    // Left edge of the card relative to the grid container
    const cardLeft = cardRect.left - gridRect.left;
    // Static column width of the 12-column grid at drag start
    const colWidth = gridRect.width / 12;

    const handleMouseMove = (moveEvent: MouseEvent) => {
      // Current mouse coordinate relative to the grid container
      const mouseX = moveEvent.clientX - gridRect.left;
      // Target card width based purely on mouse coordinate
      const desiredWidthPx = mouseX - cardLeft;
      // Convert to grid columns (1-12)
      let targetW = Math.round(desiredWidthPx / colWidth);
      
      // Clamp size to valid limits
      targetW = Math.max(3, Math.min(12, targetW));
      
      // Map to system column values: [3, 4, 6, 8, 9, 12]
      const possibleWidths = [3, 4, 6, 8, 9, 12];
      const closestW = possibleWidths.reduce((prev, curr) => {
        return Math.abs(curr - targetW) < Math.abs(prev - targetW) ? curr : prev;
      });
      
      updateWidgetProp(widgetId, "w", closestW);
    };

    const handleMouseUp = () => {
      window.removeEventListener("mousemove", handleMouseMove);
      window.removeEventListener("mouseup", handleMouseUp);
    };

    window.addEventListener("mousemove", handleMouseMove);
    window.addEventListener("mouseup", handleMouseUp);
  };

  if (isLoading) return <div className="p-8 text-center text-muted-foreground">Загрузка макета дашборда...</div>;

  const visibleWidgets = localLayout
    .map((lc) => ({
      config: lc,
      def: availableWidgets.find((w) => w.id === lc.id),
    }))
    .filter((item): item is { config: DashboardWidgetConfig; def: WidgetDefinition } => !!item.def);

  return (
    <div className={cn("space-y-6", className)}>
      {/* Dashboard Controls */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 rounded-xl border border-border bg-card/60 px-4 py-3.5 backdrop-blur-md shadow-sm">
        <div className="flex items-center gap-2.5 text-sm font-semibold">
          <div className="flex h-7.5 w-7.5 items-center justify-center rounded-lg bg-primary/10 text-primary shadow-inner">
            <Layout className="h-4 w-4" />
          </div>
          <span className="tracking-tight">{isEditing ? "Настройка рабочего пространства" : "Рабочее пространство"}</span>
          {isEditing && (
            <span className="rounded-full bg-primary/10 px-2.5 py-0.5 text-[10px] font-bold text-primary">
              Конструктор активен
            </span>
          )}
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {isEditing ? (
            <>
              <Button variant="outline" size="sm" onClick={addAllWidgets} className="h-8 text-xs font-semibold">
                <Plus className="mr-1 h-3.5 w-3.5" /> Добавить все
              </Button>
              <Button variant="ghost" size="sm" onClick={handleReset} className="h-8 gap-1.5 text-xs text-muted-foreground hover:text-foreground font-medium">
                <RotateCcw className="h-3.5 w-3.5" /> По умолчанию
              </Button>
              <Button variant="ghost" size="sm" onClick={() => setIsEditing(false)} className="h-8 gap-1.5 text-xs font-medium">
                <X className="h-3.5 w-3.5" /> Отмена
              </Button>
              <Button size="sm" onClick={handleSave} disabled={saveMutation.isPending} className="h-8 gap-1.5 text-xs font-semibold shadow-md shadow-primary/10">
                <Save className="h-3.5 w-3.5" /> Сохранить
              </Button>
            </>
          ) : (
            <Button variant="outline" size="sm" onClick={() => setIsEditing(true)} className="h-8 gap-1.5 text-xs font-semibold hover:bg-secondary/40 border-primary/20 hover:border-primary/40 text-primary hover:text-primary transition-all">
              <Settings2 className="h-3.5 w-3.5" /> Настроить виджеты
            </Button>
          )}
        </div>
      </div>

      {/* Dynamic Interaction Help Alert */}
      {isEditing && (
        <motion.div 
          initial={{ opacity: 0, y: -10 }} 
          animate={{ opacity: 1, y: 0 }}
          className="flex items-start gap-3.5 rounded-xl border border-border bg-secondary/10 p-4 text-xs text-foreground shadow-sm"
        >
          <Info className="h-5 w-5 mt-0.5 shrink-0 text-muted-foreground" />
          <div className="space-y-1">
            <strong className="font-bold text-sm block">Инструкция по настройке панелей интерфейса:</strong>
            <p className="text-[11.5px] leading-relaxed text-muted-foreground">
              • <strong>Перемещение</strong>: Нажмите и удерживайте левую кнопку мыши на верхней панели карточки виджета с иконкой <GripVertical className="inline-block h-3.5 w-3.5 mx-0.5" /> для изменения его расположения на экране.
              <br />
              • <strong>Изменение ширины границ</strong>: Наведите указатель на правый край карточки виджета и потяните его влево или вправо для точного регулирования размера по сетке.
              <br />
              • <strong>Быстрое масштабирование</strong>: Используйте кнопки <strong><Minus className="inline-block h-3 w-3" /> (сжать)</strong> и <strong><Plus className="inline-block h-3 w-3" /> (расширить)</strong> в заголовке панели для быстрого изменения сетки отображения.
            </p>
          </div>
        </motion.div>
      )}

      {/* Edit Palette (Interactive Dock) */}
      <AnimatePresence>
        {isEditing && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            className="overflow-hidden"
          >
            <div className="rounded-xl border border-dashed border-border/80 bg-secondary/10 p-5 shadow-inner space-y-4">
              <div className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground/80 flex items-center gap-1.5">
                <Layout className="h-3.5 w-3.5" /> Библиотека виджетов (нажмите для добавления/удаления с экрана)
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
                {availableWidgets.map((w) => {
                  const isActive = localLayout.some((lc) => lc.id === w.id);
                  const desc = widgetDescriptions[w.id] || "Информационная панель мониторинга.";
                  const defaultWidthText = w.defaultSize.w === 12 ? "100%" : `${Math.round((w.defaultSize.w / 12) * 100)}%`;
                  
                  return (
                    <div
                      key={w.id}
                      onClick={() => toggleWidget(w.id)}
                      className={cn(
                        "flex flex-col justify-between p-3.5 rounded-xl border transition-all cursor-pointer select-none",
                        isActive 
                          ? "bg-primary/5 border-primary/45 shadow-sm shadow-primary/5 hover:bg-primary/10" 
                          : "bg-background/45 border-border/80 hover:bg-secondary/40 hover:border-muted-foreground/30"
                      )}
                    >
                      <div className="space-y-1.5">
                        <div className="flex items-center justify-between">
                          <div className="flex items-center gap-2 font-semibold text-xs min-w-0">
                            <div className={cn(
                              "flex h-6.5 w-6.5 shrink-0 items-center justify-center rounded-lg border",
                              isActive ? "bg-primary/10 text-primary border-primary/20" : "bg-secondary text-muted-foreground"
                            )}>
                              {w.icon || <Layout className="h-3.5 w-3.5" />}
                            </div>
                            <span className="text-foreground truncate">{w.title}</span>
                          </div>
                          
                          <span className="text-[9px] font-mono text-muted-foreground/60 bg-secondary px-1.5 py-0.5 rounded shrink-0">
                            Ширина: {defaultWidthText}
                          </span>
                        </div>
                        
                        <p className="text-[10px] text-muted-foreground/80 leading-relaxed min-h-[30px] line-clamp-2">
                          {desc}
                        </p>
                      </div>

                      <div className="mt-3 flex items-center justify-between pt-2.5 border-t border-border/30">
                        <span className="text-[9px] text-muted-foreground/50">ID: {w.id}</span>
                        <div className="flex items-center gap-1.5">
                          <span className={cn(
                            "h-1.5 w-1.5 rounded-full",
                            isActive ? "bg-emerald-500" : "bg-muted-foreground/35"
                          )} />
                          <span className={cn(
                            "text-[10px] font-bold",
                            isActive ? "text-emerald-500" : "text-muted-foreground"
                          )}>
                            {isActive ? "Добавлен" : "Добавить"}
                          </span>
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Grid Area */}
      <div className="grid grid-cols-12 gap-4 relative">
        {/* Virtual 12-Column Grid Lines for Edit Mode */}
        {isEditing && (
          <div className="absolute inset-0 grid grid-cols-12 gap-4 pointer-events-none opacity-[0.025] px-0 z-0">
            {Array.from({ length: 12 }).map((_, i) => (
              <div key={i} className="h-full border-x border-dashed border-primary bg-primary/10 rounded-sm" />
            ))}
          </div>
        )}

        {visibleWidgets.map((item, idx) => {
          const wVal = item.config.w ?? item.def.defaultSize.w ?? 12;
          const gridClass = colSpanClasses[wVal] || "col-span-12";
          const hasSettings = activeSettingsWidget === item.config.id;
          const isWidgetDragged = draggedIndex === idx;
          
          return (
            <motion.div
              key={item.config.id}
              layout
              data-widget-id={item.config.id}
              transition={{ type: "spring", stiffness: 450, damping: 38 }}
              onDragOver={(e) => handleDragOver(e, idx)}
              className={cn(
                "relative transition-all duration-300 rounded-xl z-10", 
                gridClass,
                isEditing && "group ring-1 ring-border/30 hover:ring-primary/40 bg-secondary/5 border border-dashed border-border/50 p-1",
                isWidgetDragged && "opacity-35 ring-2 ring-primary border-primary shadow-xl z-30"
              )}
            >
              {/* INTERACTIVE DRAG HEADER BAR */}
              {isEditing && (
                <div 
                  draggable
                  onDragStart={(e) => handleDragStart(e, idx)}
                  onDragEnd={handleDragEnd}
                  className="relative mb-2 flex items-center justify-between gap-2 rounded-lg bg-card/95 px-3 py-2 border border-border shadow-sm text-xs backdrop-blur-sm z-10 cursor-grab active:cursor-grabbing hover:border-primary/50 hover:bg-secondary/40 transition-all select-none"
                  title="Зажмите и тащите для перемещения"
                >
                  <div className="flex items-center gap-2 min-w-0">
                    <GripVertical className="h-4 w-4 text-primary/70 shrink-0" />
                    <span className="font-bold truncate text-foreground select-none">{item.config.props?.customTitle ?? item.def.title}</span>
                    <span className="text-[9px] text-muted-foreground bg-secondary px-1.5 py-0.5 rounded font-mono shrink-0 select-none">
                      {wVal === 3 && "25%"}
                      {wVal === 4 && "33%"}
                      {wVal === 6 && "50%"}
                      {wVal === 8 && "66%"}
                      {wVal === 9 && "75%"}
                      {wVal === 12 && "100%"}
                    </span>
                  </div>
                  
                  <div className="flex items-center gap-1 shrink-0" onClick={(e) => e.stopPropagation()} draggable={false}>
                    {/* Quick Shrink/Expand buttons */}
                    <Button
                      variant="ghost"
                      size="icon"
                      onClick={() => handleShrink(item.config.id, wVal)}
                      disabled={wVal === 3}
                      className="h-6 w-6 rounded-md text-muted-foreground hover:bg-secondary disabled:opacity-40"
                      title="Уменьшить ширину"
                    >
                      <Minus className="h-3.5 w-3.5" />
                    </Button>

                    <Button
                      variant="ghost"
                      size="icon"
                      onClick={() => handleExpand(item.config.id, wVal)}
                      disabled={wVal === 12}
                      className="h-6 w-6 rounded-md text-muted-foreground hover:bg-secondary disabled:opacity-40"
                      title="Увеличить ширину"
                    >
                      <Plus className="h-3.5 w-3.5" />
                    </Button>

                    <div className="w-px h-3.5 bg-border mx-0.5" />

                    {/* Custom props toggler */}
                    <Button
                      variant={hasSettings ? "default" : "ghost"}
                      size="icon"
                      onClick={() => setActiveSettingsWidget(hasSettings ? null : item.config.id)}
                      className={cn("h-6 w-6 rounded-md text-muted-foreground", hasSettings && "text-primary-foreground")}
                      title="Настройки параметров виджета"
                    >
                      <SlidersHorizontal className="h-3.5 w-3.5" />
                    </Button>

                    <div className="w-px h-3.5 bg-border mx-0.5" />

                    {/* Delete */}
                    <Button 
                      variant="ghost" 
                      size="icon" 
                      onClick={() => toggleWidget(item.config.id)}
                      className="h-6 w-6 rounded-md hover:bg-destructive/10 text-muted-foreground hover:text-destructive"
                      title="Убрать с дашборда"
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </Button>
                  </div>
                </div>
              )}

              {/* DYNAMIC WIDGET SETTINGS PANEL */}
              {isEditing && hasSettings && (
                <motion.div
                  initial={{ opacity: 0, y: -5 }}
                  animate={{ opacity: 1, y: 0 }}
                  className="mb-3 rounded-lg border border-primary/20 bg-primary/5 p-3 text-xs space-y-3 shadow-inner"
                >
                  <div className="font-semibold text-foreground flex items-center gap-1">
                    <SlidersHorizontal className="h-3.5 w-3.5 text-primary" /> Параметры: {item.def.title}
                  </div>

                  <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
                    {/* Width setting */}
                    <div className="space-y-1">
                      <label className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground block">Предустановка ширины</label>
                      <div className="flex flex-wrap gap-1">
                        {[3, 4, 6, 8, 9, 12].map((size) => (
                          <button
                            key={size}
                            type="button"
                            onClick={() => updateWidgetProp(item.config.id, "w", size)}
                            className={cn(
                              "px-2 py-1 rounded text-[10px] font-semibold border transition-all",
                              wVal === size
                                ? "bg-primary text-primary-foreground border-primary shadow-sm"
                                : "bg-background/80 hover:bg-secondary border-border text-foreground"
                            )}
                          >
                            {size === 3 && "25%"}
                            {size === 4 && "33%"}
                            {size === 6 && "50%"}
                            {size === 8 && "66%"}
                            {size === 9 && "75%"}
                            {size === 12 && "100%"}
                          </button>
                        ))}
                      </div>
                    </div>

                    {/* Custom Title setting */}
                    <div className="space-y-1">
                      <label className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground block">Свой заголовок</label>
                      <input
                        type="text"
                        placeholder={item.def.title}
                        value={item.config.props?.customTitle ?? ""}
                        onChange={(e) => updateWidgetProp(item.config.id, "customTitle", e.target.value)}
                        className="w-full h-8 px-2.5 rounded-md border border-border bg-background hover:border-accent focus:border-primary transition-all text-xs"
                      />
                    </div>

                    {/* Tone setting */}
                    <div className="space-y-1">
                      <label className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground block">Визуальная схема (тон)</label>
                      <select
                        value={item.config.props?.tone ?? "default"}
                        onChange={(e) => updateWidgetProp(item.config.id, "tone", e.target.value)}
                        className="w-full h-8 px-2 rounded-md border border-border bg-background text-xs cursor-pointer focus:border-primary"
                      >
                        <option value="default">По умолчанию</option>
                        <option value="info">Инфо (Синий)</option>
                        <option value="success">Успех (Зеленый)</option>
                        <option value="warning">Внимание (Оранжевый)</option>
                        <option value="danger">Критический (Красный)</option>
                      </select>
                    </div>

                    {/* Items display limit for logs/lists */}
                    {["active_runs", "recent_runs", "recent_activity", "online_users", "active_terminals", "system_alerts_list", "user_alerts"].includes(item.config.id) && (
                      <div className="space-y-1">
                        <label className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground block">Лимит строк / объектов</label>
                        <select
                           value={item.config.props?.limit ?? 5}
                           onChange={(e) => updateWidgetProp(item.config.id, "limit", parseInt(e.target.value))}
                           className="w-full h-8 px-2 rounded-md border border-border bg-background text-xs cursor-pointer focus:border-primary"
                        >
                          {[3, 5, 8, 10, 15, 20].map((num) => (
                            <option key={num} value={num}>{num} элементов</option>
                          ))}
                        </select>
                      </div>
                    )}
                  </div>
                </motion.div>
              )}

              {/* RENDER THE WIDGET CONTENT */}
              <div className={cn(isEditing && "pointer-events-none opacity-90 transition-all relative")}>
                {item.def.render(item.config)}
                
                {/* Visual Glass Overlay when Editing */}
                {isEditing && (
                  <div className="absolute inset-0 bg-background/5 border border-primary/5 rounded-xl pointer-events-none" />
                )}
              </div>

              {/* INTERACTIVE DRAG RESIZE HANDLE */}
              {isEditing && (
                <div 
                  className="absolute right-0 top-0 bottom-0 w-3.5 cursor-col-resize hover:bg-primary/5 active:bg-primary/10 transition-colors z-20 flex items-center justify-end group select-none"
                  onMouseDown={(e) => handleResizeStart(e, item.config.id, wVal)}
                  title="Потяните за край для изменения ширины"
                >
                  {/* Glowing Edge Indicator */}
                  <div className="absolute right-0 top-0 bottom-0 w-1 bg-border/40 group-hover:bg-primary/60 group-active:bg-primary transition-all" />
                  
                  {/* Floating Grip Handle */}
                  <div className="mr-0.5 w-1.5 h-12 rounded-full bg-muted-foreground/35 group-hover:bg-primary group-active:bg-primary transition-all shadow-sm flex flex-col gap-0.5 items-center justify-center opacity-0 group-hover:opacity-100 duration-200">
                    <span className="w-0.5 h-0.5 rounded-full bg-primary-foreground" />
                    <span className="w-0.5 h-0.5 rounded-full bg-primary-foreground" />
                    <span className="w-0.5 h-0.5 rounded-full bg-primary-foreground" />
                  </div>
                </div>
              )}
            </motion.div>
          );
        })}

        {visibleWidgets.length === 0 && (
          <div className="col-span-12 py-16 text-center border-2 border-dashed rounded-2xl border-border bg-card/30 backdrop-blur-md">
            <Layout className="h-10 w-10 text-muted-foreground/40 mx-auto mb-3" />
            <h3 className="font-semibold text-foreground/80 mb-1">Дашборд пуст</h3>
            <p className="text-xs text-muted-foreground max-w-sm mx-auto mb-4">
              Нажмите кнопку "Настроить виджеты", чтобы добавить информационные панели на экран.
            </p>
            <Button variant="outline" size="sm" onClick={() => setIsEditing(true)}>
              Начать настройку
            </Button>
          </div>
        )}
      </div>
    </div>
  );
}
