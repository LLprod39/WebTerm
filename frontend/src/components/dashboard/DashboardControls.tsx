import { motion } from "framer-motion";
import { GripVertical, Info, Layout, Minus, Plus, RotateCcw, Save, Settings2, X } from "lucide-react";

import { Button } from "@/components/ui/button";

export function DashboardControls({
  isEditing,
  saving,
  onAddAllWidgets,
  onCancelEditing,
  onReset,
  onSave,
  onStartEditing,
}: {
  isEditing: boolean;
  saving: boolean;
  onAddAllWidgets: () => void;
  onCancelEditing: () => void;
  onReset: () => void;
  onSave: () => void;
  onStartEditing: () => void;
}) {
  return (
    <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 rounded-xl border border-border bg-card/60 px-4 py-3.5 backdrop-blur-md shadow-sm">
      <div className="flex items-center gap-2.5 text-sm font-semibold">
        <div className="flex h-7.5 w-7.5 items-center justify-center rounded-lg bg-primary/10 text-primary shadow-inner">
          <Layout className="h-4 w-4" />
        </div>
        <span className="tracking-tight">{isEditing ? "Настройка рабочего пространства" : "Рабочее пространство"}</span>
        {isEditing ? (
          <span className="rounded-full bg-primary/10 px-2.5 py-0.5 text-xs font-bold text-primary">
            Конструктор активен
          </span>
        ) : null}
      </div>
      <div className="flex flex-wrap items-center gap-2">
        {isEditing ? (
          <>
            <Button variant="outline" size="sm" onClick={onAddAllWidgets} className="h-8 text-xs font-semibold">
              <Plus className="mr-1 h-3.5 w-3.5" /> Добавить все
            </Button>
            <Button variant="ghost" size="sm" onClick={onReset} className="h-8 gap-1.5 text-xs text-muted-foreground hover:text-foreground font-medium">
              <RotateCcw className="h-3.5 w-3.5" /> По умолчанию
            </Button>
            <Button variant="ghost" size="sm" onClick={onCancelEditing} className="h-8 gap-1.5 text-xs font-medium">
              <X className="h-3.5 w-3.5" /> Отмена
            </Button>
            <Button size="sm" onClick={onSave} disabled={saving} className="h-8 gap-1.5 text-xs font-semibold shadow-md shadow-primary/10">
              <Save className="h-3.5 w-3.5" /> Сохранить
            </Button>
          </>
        ) : (
          <Button
            variant="outline"
            size="sm"
            onClick={onStartEditing}
            className="h-8 gap-1.5 text-xs font-semibold hover:bg-secondary/40 border-primary/20 hover:border-primary/40 text-primary hover:text-primary transition-all"
          >
            <Settings2 className="h-3.5 w-3.5" /> Настроить виджеты
          </Button>
        )}
      </div>
    </div>
  );
}

export function DashboardEditHelp({ isEditing }: { isEditing: boolean }) {
  if (!isEditing) return null;
  return (
    <motion.div
      initial={{ opacity: 0, y: -10 }}
      animate={{ opacity: 1, y: 0 }}
      className="flex items-start gap-3.5 rounded-xl border border-border bg-secondary/10 p-4 text-xs text-foreground shadow-sm"
    >
      <Info className="h-5 w-5 mt-0.5 shrink-0 text-muted-foreground" />
      <div className="space-y-1">
        <strong className="font-bold text-sm block">Инструкция по настройке панелей интерфейса:</strong>
        <p className="text-xs leading-relaxed text-muted-foreground">
          • <strong>Перемещение</strong>: Нажмите и удерживайте левую кнопку мыши на верхней панели карточки виджета с иконкой <GripVertical className="inline-block h-3.5 w-3.5 mx-0.5" /> для изменения его расположения на экране.
          <br />
          • <strong>Изменение ширины границ</strong>: Наведите указатель на правый край карточки виджета и потяните его влево или вправо для точного регулирования размера по сетке.
          <br />
          • <strong>Быстрое масштабирование</strong>: Используйте кнопки <strong><Minus className="inline-block h-3 w-3" /> (сжать)</strong> и <strong><Plus className="inline-block h-3 w-3" /> (расширить)</strong> в заголовке панели для быстрого изменения сетки отображения.
        </p>
      </div>
    </motion.div>
  );
}
