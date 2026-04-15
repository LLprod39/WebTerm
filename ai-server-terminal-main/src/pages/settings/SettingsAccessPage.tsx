import { Link } from "react-router-dom";
import { Users, FolderOpen, Shield, ChevronRight, UserCheck, KeyRound } from "lucide-react";
import { cn } from "@/lib/utils";

const accessPages = [
  {
    title: "Пользователи",
    description: "Управление аккаунтами, профилями доступа и группами пользователя",
    icon: Users,
    url: "/settings/users",
    color: "text-blue-400",
    bgColor: "bg-blue-500/10",
  },
  {
    title: "Группы",
    description: "Команды, участники и общая политика доступа для группы",
    icon: FolderOpen,
    url: "/settings/groups",
    color: "text-emerald-400",
    bgColor: "bg-emerald-500/10",
  },
  {
    title: "Разрешения",
    description: "Точечные allow/deny правила для исключений из общей политики",
    icon: Shield,
    url: "/settings/permissions",
    color: "text-amber-400",
    bgColor: "bg-amber-500/10",
  },
];

const quickActions = [
  {
    title: "Добавить пользователя",
    description: "Создать новый аккаунт",
    icon: UserCheck,
    url: "/settings/users?action=create",
  },
  {
    title: "Настроить роли",
    description: "Редактировать группы доступа",
    icon: KeyRound,
    url: "/settings/groups",
  },
];

export default function SettingsAccessPage() {
  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div>
        <h1 className="text-xl font-semibold text-foreground">Управление доступом</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Пользователи, группы и разрешения для контроля доступа к платформе
        </p>
      </div>

      {/* Info Banner */}
      <div className="rounded-xl border border-border bg-secondary/20 px-5 py-4">
        <p className="text-sm leading-relaxed text-muted-foreground">
          Базовую модель прав лучше собирать через профили и группы. 
          Раздел разрешений используй только там, где действительно нужно сделать исключение.
        </p>
      </div>

      {/* Main Navigation Cards */}
      <div className="overflow-hidden rounded-xl border border-border">
        {accessPages.map((page, index, pages) => (
          <Link
            key={page.url}
            to={page.url}
            className={cn(
              "group flex items-center gap-4 bg-card px-5 py-5 transition-colors hover:bg-secondary/30",
              index < pages.length - 1 && "border-b border-border"
            )}
          >
            <div className={cn("flex h-12 w-12 shrink-0 items-center justify-center rounded-xl", page.bgColor)}>
              <page.icon className={cn("h-5 w-5", page.color)} aria-hidden="true" />
            </div>
            <div className="min-w-0 flex-1">
              <p className="text-sm font-medium text-foreground">{page.title}</p>
              <p className="mt-0.5 text-sm text-muted-foreground">{page.description}</p>
            </div>
            <ChevronRight className="h-5 w-5 shrink-0 text-muted-foreground transition-transform group-hover:translate-x-0.5 group-hover:text-foreground" aria-hidden="true" />
          </Link>
        ))}
      </div>

      {/* Quick Actions */}
      <div>
        <h2 className="mb-3 text-sm font-medium text-foreground">Быстрые действия</h2>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          {quickActions.map((action) => (
            <Link
              key={action.url}
              to={action.url}
              className="group flex items-center gap-3 rounded-lg border border-border bg-card px-4 py-3 transition-colors hover:bg-secondary/30"
            >
              <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-secondary/50 transition-colors group-hover:bg-secondary">
                <action.icon className="h-4 w-4 text-muted-foreground" />
              </div>
              <div className="min-w-0 flex-1">
                <p className="text-sm font-medium text-foreground">{action.title}</p>
                <p className="text-xs text-muted-foreground">{action.description}</p>
              </div>
            </Link>
          ))}
        </div>
      </div>

      {/* Help Section */}
      <div className="rounded-xl border border-dashed border-border bg-secondary/10 px-5 py-4">
        <h3 className="text-sm font-medium text-foreground">Как работает система доступа</h3>
        <div className="mt-3 space-y-2 text-sm text-muted-foreground">
          <p>
            <strong className="text-foreground">1. Пользователи</strong> - создавайте аккаунты и назначайте профили доступа
          </p>
          <p>
            <strong className="text-foreground">2. Группы</strong> - объединяйте пользователей с одинаковыми правами
          </p>
          <p>
            <strong className="text-foreground">3. Разрешения</strong> - настраивайте точечные исключения при необходимости
          </p>
        </div>
      </div>
    </div>
  );
}
