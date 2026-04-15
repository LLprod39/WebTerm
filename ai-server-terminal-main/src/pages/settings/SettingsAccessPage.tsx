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
    bgColor: "bg-blue-500/12",
  },
  {
    title: "Группы",
    description: "Команды, участники и общая политика доступа для группы",
    icon: FolderOpen,
    url: "/settings/groups",
    color: "text-violet-400",
    bgColor: "bg-violet-500/12",
  },
  {
    title: "Разрешения",
    description: "Точечные allow/deny правила для исключений из общей политики",
    icon: Shield,
    url: "/settings/permissions",
    color: "text-amber-400",
    bgColor: "bg-amber-500/12",
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
    <div className="space-y-6 pb-10">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold tracking-tight text-foreground">Управление доступом</h1>
        <p className="mt-1 text-sm text-muted-foreground/70">
          Пользователи, группы и точечные разрешения для контроля доступа к платформе
        </p>
      </div>

      {/* Info */}
      <div className="rounded-xl border border-white/[0.06] bg-white/[0.02] px-5 py-4">
        <p className="text-sm leading-relaxed text-muted-foreground/70">
          Базовую модель прав лучше собирать через <strong className="text-foreground/80 font-medium">профили</strong> и <strong className="text-foreground/80 font-medium">группы</strong>.
          Раздел <strong className="text-foreground/80 font-medium">разрешений</strong> используй только там, где действительно нужно сделать точечное исключение.
        </p>
      </div>

      {/* Navigation cards */}
      <div className="rounded-xl border border-white/[0.06] bg-white/[0.015] overflow-hidden">
        {accessPages.map((page, index, pages) => (
          <Link
            key={page.url}
            to={page.url}
            className={cn(
              "group flex items-center gap-4 px-5 py-5 transition-all duration-200 hover:bg-white/[0.03]",
              index < pages.length - 1 && "border-b border-white/[0.04]"
            )}
          >
            <div className={cn("flex h-11 w-11 shrink-0 items-center justify-center rounded-xl transition-transform duration-200 group-hover:scale-105", page.bgColor)}>
              <page.icon className={cn("h-5 w-5", page.color)} aria-hidden="true" />
            </div>
            <div className="min-w-0 flex-1">
              <p className="text-sm font-semibold text-foreground/90 transition-colors group-hover:text-foreground">{page.title}</p>
              <p className="mt-0.5 text-xs text-muted-foreground/60">{page.description}</p>
            </div>
            <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg text-muted-foreground/30 transition-all duration-200 group-hover:bg-white/[0.04] group-hover:text-foreground/60 group-hover:translate-x-0.5">
              <ChevronRight className="h-4 w-4" aria-hidden="true" />
            </div>
          </Link>
        ))}
      </div>

      {/* Quick actions */}
      <div>
        <h2 className="mb-3 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground/60">Быстрые действия</h2>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          {quickActions.map((action) => (
            <Link
              key={action.url}
              to={action.url}
              className="group flex items-center gap-3 rounded-xl border border-white/[0.06] bg-white/[0.015] px-4 py-3.5 transition-all duration-200 hover:bg-white/[0.03] hover:border-white/[0.1]"
            >
              <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary transition-colors duration-200 group-hover:bg-primary group-hover:text-primary-foreground">
                <action.icon className="h-4 w-4" />
              </div>
              <div className="min-w-0 flex-1">
                <p className="text-sm font-medium text-foreground/90">{action.title}</p>
                <p className="text-[11px] text-muted-foreground/50">{action.description}</p>
              </div>
            </Link>
          ))}
        </div>
      </div>

      {/* How it works */}
      <div className="rounded-xl border border-dashed border-white/[0.08] bg-white/[0.01] px-5 py-5">
        <h3 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground/60 flex items-center gap-2">
          <div className="h-1.5 w-1.5 rounded-full bg-primary/60" />
          Как работает система доступа
        </h3>
        <div className="mt-4 space-y-3 text-[13px] text-muted-foreground/60">
          <p className="flex items-start gap-2.5">
            <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-md bg-white/[0.04] text-[10px] font-bold text-muted-foreground/70 mt-px">1</span>
            <span><strong className="text-foreground/70 font-medium">Пользователи</strong> — создавайте аккаунты и назначайте профили доступа.</span>
          </p>
          <p className="flex items-start gap-2.5">
            <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-md bg-white/[0.04] text-[10px] font-bold text-muted-foreground/70 mt-px">2</span>
            <span><strong className="text-foreground/70 font-medium">Группы</strong> — объединяйте пользователей с одинаковыми правами.</span>
          </p>
          <p className="flex items-start gap-2.5">
            <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-md bg-white/[0.04] text-[10px] font-bold text-muted-foreground/70 mt-px">3</span>
            <span><strong className="text-foreground/70 font-medium">Разрешения</strong> — настраивайте точечные исключения при необходимости.</span>
          </p>
        </div>
      </div>
    </div>
  );
}
