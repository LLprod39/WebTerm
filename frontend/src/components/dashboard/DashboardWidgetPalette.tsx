import { AnimatePresence, motion } from "framer-motion";
import { Layout } from "lucide-react";

import { cn } from "@/lib/utils";

import {
  dashboardWidgetDescriptions,
  getDashboardWidthLabel,
} from "./dashboardLayoutModel";
import type { WidgetDefinition } from "./dashboardTypes";

export function DashboardWidgetPalette({
  availableWidgets,
  isEditing,
  localWidgetIds,
  onToggleWidget,
}: {
  availableWidgets: WidgetDefinition[];
  isEditing: boolean;
  localWidgetIds: string[];
  onToggleWidget: (id: string) => void;
}) {
  return (
    <AnimatePresence>
      {isEditing ? (
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
              {availableWidgets.map((widget) => {
                const isActive = localWidgetIds.includes(widget.id);
                const description = dashboardWidgetDescriptions[widget.id] || "Информационная панель мониторинга.";
                const defaultWidthText = getDashboardWidthLabel(widget.defaultSize.w);

                return (
                  <div
                    key={widget.id}
                    onClick={() => onToggleWidget(widget.id)}
                    className={cn(
                      "flex flex-col justify-between p-3.5 rounded-xl border transition-all cursor-pointer select-none",
                      isActive
                        ? "bg-primary/5 border-primary/45 shadow-sm shadow-primary/5 hover:bg-primary/10"
                        : "bg-background/45 border-border/80 hover:bg-secondary/40 hover:border-muted-foreground/30",
                    )}
                  >
                    <div className="space-y-1.5">
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-2 font-semibold text-xs min-w-0">
                          <div
                            className={cn(
                              "flex h-6.5 w-6.5 shrink-0 items-center justify-center rounded-lg border",
                              isActive ? "bg-primary/10 text-primary border-primary/20" : "bg-secondary text-muted-foreground",
                            )}
                          >
                            {widget.icon || <Layout className="h-3.5 w-3.5" />}
                          </div>
                          <span className="text-foreground truncate">{widget.title}</span>
                        </div>

                        <span className="text-[9px] font-mono text-muted-foreground/60 bg-secondary px-1.5 py-0.5 rounded shrink-0">
                          Ширина: {defaultWidthText}
                        </span>
                      </div>

                      <p className="text-[10px] text-muted-foreground/80 leading-relaxed min-h-[30px] line-clamp-2">
                        {description}
                      </p>
                    </div>

                    <div className="mt-3 flex items-center justify-between pt-2.5 border-t border-border/30">
                      <span className="text-[9px] text-muted-foreground/50">ID: {widget.id}</span>
                      <div className="flex items-center gap-1.5">
                        <span className={cn("h-1.5 w-1.5 rounded-full", isActive ? "bg-emerald-500" : "bg-muted-foreground/35")} />
                        <span className={cn("text-[10px] font-bold", isActive ? "text-emerald-500" : "text-muted-foreground")}>
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
      ) : null}
    </AnimatePresence>
  );
}
