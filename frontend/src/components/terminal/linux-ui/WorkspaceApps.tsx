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
      title: localize(lang, "Файлы", "Files"),
      subtitle: localize(lang, "Папки и передача файлов", "Folders and file transfers"),
      status: "live",
      icon: <FolderOpen className="h-5 w-5" />,
      accentClass: "from-primary/20 to-secondary",
    },
    {
      id: "overview",
      title: localize(lang, "Обзор", "Overview"),
      subtitle: localize(lang, "Состояние хоста", "Host status"),
      status: "live",
      icon: <Monitor className="h-5 w-5" />,
      accentClass: "from-primary/15 to-background",
      // Beta surface — hidden for pilot (not in dock/launcher).
      hidden: true,
    },
    {
      id: "services",
      title: localize(lang, "Сервисы", "Services"),
      subtitle: availableApps?.services ? localize(lang, "Управление через systemctl", "Managed through systemctl") : localize(lang, "Недоступно на этом хосте", "Unavailable on this host"),
      status: availableApps?.services ? "live" : "unavailable",
      icon: <Settings2 className="h-5 w-5" />,
      accentClass: "from-secondary to-background",
    },
    {
      id: "processes",
      title: localize(lang, "Процессы", "Processes"),
      subtitle: localize(lang, "Нагрузка на CPU и память", "CPU and memory usage"),
      status: "live",
      icon: <Activity className="h-5 w-5" />,
      accentClass: "from-primary/12 to-secondary",
    },
    {
      id: "logs",
      title: localize(lang, "Логи", "Logs"),
      subtitle: availableApps?.logs ? localize(lang, "journalctl и файловые источники", "journalctl and file sources") : localize(lang, "Файловые логи и systemctl", "File logs and systemctl"),
      status: "live",
      icon: <FileText className="h-5 w-5" />,
      accentClass: "from-primary/18 to-secondary",
    },
    {
      id: "disk",
      title: localize(lang, "Диск", "Disk"),
      subtitle: availableApps?.disk ? localize(lang, "Использование и очистка", "Usage and cleanup") : localize(lang, "Проверка диска недоступна", "Disk inspection unavailable"),
      status: availableApps?.disk ? "live" : "unavailable",
      icon: <HardDrive className="h-5 w-5" />,
      accentClass: "from-secondary to-background",
    },
    {
      id: "network",
      title: localize(lang, "Сеть", "Network"),
      subtitle: availableApps?.network ? localize(lang, "Интерфейсы и порты", "Interfaces and ports") : localize(lang, "Сетевые инструменты не найдены", "Network tools not found"),
      status: availableApps?.network ? "live" : "unavailable",
      icon: <Network className="h-5 w-5" />,
      accentClass: "from-primary/16 to-background",
    },
    {
      id: "docker",
      title: "Docker",
      subtitle: availableApps?.docker ? localize(lang, "Контейнеры и логи", "Containers and logs") : localize(lang, "Docker не найден", "Docker not found"),
      status: availableApps?.docker ? "live" : "unavailable",
      icon: <Server className="h-5 w-5" />,
      accentClass: "from-secondary to-background",
    },
    {
      id: "packages",
      title: localize(lang, "Пакеты", "Packages"),
      subtitle: packageManager ? localize(lang, `Менеджер пакетов: ${packageManager}`, `Package manager: ${packageManager}`) : localize(lang, "Менеджер пакетов не найден", "Package manager not found"),
      status: packageManager ? "live" : "unavailable",
      icon: <Package className="h-5 w-5" />,
      accentClass: "from-primary/15 to-secondary",
    },
    {
      id: "text-editor",
      title: localize(lang, "Редактор", "Editor"),
      subtitle: availableApps?.text_editor ? localize(lang, "Конфигурации и скрипты", "Configuration and scripts") : localize(lang, "Редактор недоступен на этом хосте", "Editor unavailable on this host"),
      status: availableApps?.text_editor ? "live" : "unavailable",
      icon: <FileCode2 className="h-5 w-5" />,
      accentClass: "from-primary/18 to-background",
      hidden: true,
    },
    {
      id: "quick-run",
      title: localize(lang, "Быстрый запуск", "Quick run"),
      subtitle: availableApps?.quick_run ? localize(lang, "Команда и результат", "Command and result") : localize(lang, "Выполнение команд недоступно", "Command execution unavailable"),
      status: availableApps?.quick_run ? "live" : "unavailable",
      icon: <Terminal className="h-5 w-5" />,
      accentClass: "from-secondary to-background",
    },
    {
      id: "settings",
      title: localize(lang, "Настройки", "Settings"),
      subtitle: availableApps?.settings ? localize(lang, "Система, пользователи, cron и безопасность", "System, users, cron, and security") : localize(lang, "Данные настроек недоступны", "Settings data unavailable"),
      status: availableApps?.settings ? "live" : "unavailable",
      icon: <Settings className="h-5 w-5" />,
      accentClass: "from-muted to-background",
    },
  ];
}
