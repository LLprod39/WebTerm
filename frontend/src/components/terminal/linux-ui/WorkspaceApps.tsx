import {
  Activity,
  FileCode2,
  FileText,
  FolderOpen,
  HardDrive,
  Monitor,
  Network,
  Package,
  Server,
  Settings,
  Settings2,
  Terminal,
} from "lucide-react";

import type { WorkspaceAppDefinition } from "@/components/terminal/linux-ui/WorkspaceChrome";
import type { LinuxUiCapabilities } from "@/lib/api";
import { localize } from "@/lib/i18n";

interface BuildWorkspaceAppsOptions {
  availableApps: LinuxUiCapabilities["available_apps"] | undefined;
  packageManager: LinuxUiCapabilities["package_manager"] | undefined;
  lang: string;
}

export function buildWorkspaceApps({
  availableApps,
  packageManager,
  lang,
}: BuildWorkspaceAppsOptions): WorkspaceAppDefinition[] {
  return [
    {
      id: "files",
      title: "Файлы",
      subtitle: "Папки, загрузки, удаление и переименование",
      status: "live",
      icon: <FolderOpen className="h-5 w-5" />,
      accentClass: "from-primary/20 to-secondary",
    },
    {
      id: "overview",
      title: "Обзор",
      subtitle: "Сводка хоста и системные маркеры",
      status: "live",
      icon: <Monitor className="h-5 w-5" />,
      accentClass: "from-primary/15 to-background",
      // Beta surface — hidden for pilot (not in dock/launcher).
      hidden: true,
    },
    {
      id: "services",
      title: "Сервисы",
      subtitle: availableApps?.services ? "Управление systemctl доступно" : "Недоступно на этом хосте",
      status: availableApps?.services ? "live" : "unavailable",
      icon: <Settings2 className="h-5 w-5" />,
      accentClass: "from-secondary to-background",
    },
    {
      id: "processes",
      title: "Процессы",
      subtitle: "Процессы по CPU и памяти",
      status: "live",
      icon: <Activity className="h-5 w-5" />,
      accentClass: "from-primary/12 to-secondary",
    },
    {
      id: "logs",
      title: "Логи",
      subtitle: availableApps?.logs ? "journalctl и file presets доступны" : "Доступны file presets и service fallback",
      status: "live",
      icon: <FileText className="h-5 w-5" />,
      accentClass: "from-primary/18 to-secondary",
    },
    {
      id: "disk",
      title: "Диск",
      subtitle: availableApps?.disk ? "Использование и сигналы очистки" : "Инспекция диска недоступна",
      status: availableApps?.disk ? "live" : "unavailable",
      icon: <HardDrive className="h-5 w-5" />,
      accentClass: "from-secondary to-background",
    },
    {
      id: "network",
      title: "Сеть",
      subtitle: availableApps?.network ? "Интерфейсы и порты доступны" : "Сетевые инструменты не найдены",
      status: availableApps?.network ? "live" : "unavailable",
      icon: <Network className="h-5 w-5" />,
      accentClass: "from-primary/16 to-background",
    },
    {
      id: "docker",
      title: "Docker",
      subtitle: availableApps?.docker ? "Контейнеры и логи доступны" : "Docker не найден",
      status: availableApps?.docker ? "live" : "unavailable",
      icon: <Server className="h-5 w-5" />,
      accentClass: "from-secondary to-background",
    },
    {
      id: "packages",
      title: "Пакеты",
      subtitle: packageManager ? `Инспектор ${packageManager} доступен` : localize(lang, "Менеджер пакетов не найден", "Package manager not found"),
      status: packageManager ? "live" : "unavailable",
      icon: <Package className="h-5 w-5" />,
      accentClass: "from-primary/15 to-secondary",
    },
    {
      id: "text-editor",
      title: "Редактор",
      subtitle: availableApps?.text_editor ? "Редактирование config-файлов" : "Редактор недоступен на этом хосте",
      status: availableApps?.text_editor ? "live" : "unavailable",
      icon: <FileCode2 className="h-5 w-5" />,
      accentClass: "from-primary/18 to-background",
      hidden: true,
    },
    {
      id: "quick-run",
      title: "Быстрый запуск",
      subtitle: availableApps?.quick_run ? "Команды с выводом результата" : localize(lang, "Выполнение shell-команд недоступно", "Shell execution unavailable"),
      status: availableApps?.quick_run ? "live" : "unavailable",
      icon: <Terminal className="h-5 w-5" />,
      accentClass: "from-secondary to-background",
    },
    {
      id: "settings",
      title: "Настройки",
      subtitle: availableApps?.settings ? "Система, пользователи, cron, безопасность" : "Снимок настроек недоступен",
      status: availableApps?.settings ? "live" : "unavailable",
      icon: <Settings className="h-5 w-5" />,
      accentClass: "from-muted to-background",
    },
  ];
}
