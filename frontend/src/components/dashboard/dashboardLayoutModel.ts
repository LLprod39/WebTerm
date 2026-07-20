import type { DashboardWidgetConfig } from "@/lib/api";

import type { DashboardType, VisibleDashboardWidget, WidgetDefinition } from "./dashboardTypes";

export const DASHBOARD_WIDGET_WIDTHS = [3, 4, 6, 8, 9, 12] as const;

export const dashboardColSpanClasses: Record<number, string> = {
  3: "col-span-12 md:col-span-3 lg:col-span-3",
  4: "col-span-12 md:col-span-4 lg:col-span-4",
  6: "col-span-12 md:col-span-6 lg:col-span-6",
  8: "col-span-12 md:col-span-8 lg:col-span-8",
  9: "col-span-12 md:col-span-9 lg:col-span-9",
  12: "col-span-12",
};

export const dashboardWidgetDescriptions: Record<string, string> = {
  attention_panel: "Триаж-панель: все проблемы платформы в одном месте с кнопками быстрого перехода.",
  fleet_heatmap: "Карта флота: плитка на каждый сервер с загрузкой CPU/RAM/диска и статусом.",
  agents_trend: "Тренд запусков агентов за 7 дней: успешные и сбойные по дням.",
  my_attention: "Ваши проблемы: сбои агентов, алерты и недоступные серверы с быстрыми действиями.",
  quick_stats: "Краткая сводка с ключевыми метриками ваших серверов, активных агентов и алертов.",
  servers_health: "Состояние и загрузка CPU/RAM серверов с быстрыми ссылками на терминал.",
  quick_tools: "Панель быстрых действий для мгновенного перехода в Хаб серверов, Студию или Настройки.",
  active_runs: "Список запущенных в данный момент агентов с отслеживанием статуса.",
  recent_runs: "История последних завершенных запусков агентов с метриками и временем.",
  user_alerts: "Список последних активных предупреждений и критических алертов по серверам.",
  recent_activity: "Лог ваших последних действий в системе с временными метками.",
  recent_servers: "Быстрый доступ к вашим недавно подключенным серверам и их терминалам.",
  fleet_metrics: "Инфраструктурные метрики: общее число серверов, средняя нагрузка и алерты.",
  hourly_activity_chart: "Интерактивный график активности системы за последние 24 часа.",
  ai_cost_tokens: "Анализ затрат на LLM, количество токенов и ошибок по каждому провайдеру.",
  active_providers: "Статус доступности и активные модели провайдеров.",
  online_users: "Список пользователей, находящихся сейчас в системе, и их действия.",
  top_users: "Рейтинг наиболее активных пользователей по операциям и запросам.",
  active_terminals: "Список активных в данный момент SSH терминальных сессий.",
  system_alerts_list: "Критические инфраструктурные алерты, требующие внимания администратора.",
};

export const dashboardLimitedListWidgetIds = new Set([
  "attention_panel",
  "my_attention",
  "active_runs",
  "recent_runs",
  "recent_activity",
  "online_users",
  "active_terminals",
  "system_alerts_list",
  "user_alerts",
]);

export function getDashboardWidthLabel(width: number): string {
  if (width === 3) return "25%";
  if (width === 4) return "33%";
  if (width === 6) return "50%";
  if (width === 8) return "66%";
  if (width === 9) return "75%";
  return "100%";
}

export function getCuratedDefaultDashboardLayout(type: DashboardType): DashboardWidgetConfig[] {
  if (type === "user") {
    // Mirrors the admin layout's structure with the widgets a regular user can
    // populate: attention full-width on top, a metrics row, runs, then an
    // alerts + servers row and a full-width activity log at the bottom.
    return [
      { id: "my_attention", x: 0, y: 0, w: 12, h: 1, props: { tone: "default", limit: 6 } },
      { id: "quick_stats", x: 0, y: 1, w: 12, h: 1, props: { tone: "default", limit: 5 } },
      { id: "servers_health", x: 0, y: 2, w: 8, h: 1, props: { tone: "default", limit: 5 } },
      { id: "quick_tools", x: 8, y: 2, w: 4, h: 1, props: { tone: "default", limit: 5 } },
      { id: "active_runs", x: 0, y: 3, w: 6, h: 1, props: { tone: "default", limit: 5 } },
      { id: "recent_runs", x: 6, y: 3, w: 6, h: 1, props: { tone: "default", limit: 5 } },
      { id: "user_alerts", x: 0, y: 4, w: 6, h: 1, props: { tone: "default", limit: 5 } },
      { id: "recent_servers", x: 6, y: 4, w: 6, h: 1, props: { tone: "default", limit: 5 } },
      { id: "recent_activity", x: 0, y: 5, w: 12, h: 1, props: { tone: "default", limit: 5 } },
    ];
  }
  return [
    { id: "attention_panel", x: 0, y: 0, w: 12, h: 1, props: { tone: "default", limit: 6 } },
    { id: "fleet_metrics", x: 0, y: 1, w: 12, h: 1, props: { tone: "default", limit: 5 } },
    { id: "fleet_heatmap", x: 0, y: 2, w: 8, h: 1, props: { tone: "default", limit: 5 } },
    { id: "agents_trend", x: 8, y: 2, w: 4, h: 1, props: { tone: "default", limit: 5 } },
    { id: "hourly_activity_chart", x: 0, y: 3, w: 8, h: 1, props: { tone: "default", limit: 5 } },
    { id: "active_providers", x: 8, y: 3, w: 4, h: 1, props: { tone: "default", limit: 5 } },
    { id: "ai_cost_tokens", x: 0, y: 4, w: 8, h: 1, props: { tone: "default", limit: 5 } },
    { id: "active_terminals", x: 8, y: 4, w: 4, h: 1, props: { tone: "default", limit: 5 } },
    { id: "top_users", x: 0, y: 5, w: 6, h: 1, props: { tone: "default", limit: 5 } },
    { id: "online_users", x: 6, y: 5, w: 6, h: 1, props: { tone: "default", limit: 5 } },
    { id: "system_alerts_list", x: 0, y: 6, w: 6, h: 1, props: { tone: "default", limit: 5 } },
    { id: "recent_activity", x: 6, y: 6, w: 6, h: 1, props: { tone: "default", limit: 5 } },
  ];
}

export function validateSavedDashboardLayout(
  widgets: DashboardWidgetConfig[],
  availableWidgets: WidgetDefinition[],
): DashboardWidgetConfig[] {
  return widgets.map((layoutConfig) => {
    const definition = availableWidgets.find((widget) => widget.id === layoutConfig.id);
    return {
      ...layoutConfig,
      w: layoutConfig.w && DASHBOARD_WIDGET_WIDTHS.includes(layoutConfig.w as never)
        ? layoutConfig.w
        : definition?.defaultSize.w || 12,
    };
  });
}

export function getInitialDashboardLayout({
  availableWidgets,
  savedWidgets,
  type,
}: {
  availableWidgets: WidgetDefinition[];
  savedWidgets?: DashboardWidgetConfig[] | null;
  type: DashboardType;
}): DashboardWidgetConfig[] {
  if (savedWidgets) return validateSavedDashboardLayout(savedWidgets, availableWidgets);
  const filtered = getCuratedDefaultDashboardLayout(type).filter((preset) =>
    availableWidgets.some((widget) => widget.id === preset.id),
  );
  if (filtered.length) return filtered;
  return availableWidgets.map((widget, index) => ({
    id: widget.id,
    x: 0,
    y: index,
    w: widget.defaultSize.w || 12,
    h: 1,
    props: { tone: "default", limit: 5 },
  }));
}

export function getVisibleDashboardWidgets(
  layout: DashboardWidgetConfig[],
  availableWidgets: WidgetDefinition[],
): VisibleDashboardWidget[] {
  return layout
    .map((config) => ({
      config,
      def: availableWidgets.find((widget) => widget.id === config.id),
    }))
    .filter((item): item is VisibleDashboardWidget => Boolean(item.def));
}

export function getMissingDashboardWidgets(
  layout: DashboardWidgetConfig[],
  availableWidgets: WidgetDefinition[],
): DashboardWidgetConfig[] {
  const currentIds = layout.map((widget) => widget.id);
  return availableWidgets
    .filter((widget) => !currentIds.includes(widget.id))
    .map((widget, index) => ({
      id: widget.id,
      x: 0,
      y: layout.length + index,
      w: widget.defaultSize.w || 12,
      h: 1,
      props: { tone: "default", limit: 5 },
    }));
}

export function toggleDashboardWidget(
  layout: DashboardWidgetConfig[],
  availableWidgets: WidgetDefinition[],
  id: string,
): DashboardWidgetConfig[] {
  if (layout.some((widget) => widget.id === id)) {
    return layout.filter((widget) => widget.id !== id);
  }
  const definition = availableWidgets.find((widget) => widget.id === id);
  return [
    ...layout,
    {
      id,
      x: 0,
      y: layout.length,
      w: definition?.defaultSize.w || 12,
      h: 1,
      props: { tone: "default", limit: 5 },
    },
  ];
}

export function updateDashboardWidgetProp(
  layout: DashboardWidgetConfig[],
  id: string,
  key: string,
  value: string | number,
): DashboardWidgetConfig[] {
  return layout.map((widget) => {
    if (widget.id !== id) return widget;
    if (key === "w") {
      return { ...widget, w: Number.isFinite(Number(value)) ? Number(value) : widget.w };
    }
    return {
      ...widget,
      props: {
        ...(widget.props ?? {}),
        [key]: value,
      },
    };
  });
}

export function getAdjacentDashboardWidth(currentWidth: number, direction: -1 | 1): number {
  const currentIndex = DASHBOARD_WIDGET_WIDTHS.indexOf(currentWidth as never);
  if (currentIndex < 0) return currentWidth;
  const nextIndex = currentIndex + direction;
  if (nextIndex < 0 || nextIndex >= DASHBOARD_WIDGET_WIDTHS.length) return currentWidth;
  return DASHBOARD_WIDGET_WIDTHS[nextIndex];
}

export function getClosestDashboardWidth(targetWidth: number): number {
  return DASHBOARD_WIDGET_WIDTHS.reduce((previous, current) =>
    Math.abs(current - targetWidth) < Math.abs(previous - targetWidth) ? current : previous,
  );
}
