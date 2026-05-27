import { Link } from "react-router-dom";
import { Users, FolderOpen, Shield, ChevronRight, UserCheck, KeyRound, Lock } from "lucide-react";
import { cn } from "@/lib/utils";
import { useI18n } from "@/lib/i18n";

export default function SettingsAccessPage() {
  const { t } = useI18n();

  const accessPages = [
    { titleKey: "access.users", descKey: "access.users_desc", icon: Users, url: "/settings/users", color: "text-blue-400", bgColor: "bg-blue-500/12" },
    { titleKey: "access.groups", descKey: "access.groups_desc", icon: FolderOpen, url: "/settings/groups", color: "text-violet-400", bgColor: "bg-violet-500/12" },
    { titleKey: "access.permissions", descKey: "access.permissions_desc", icon: Shield, url: "/settings/permissions", color: "text-amber-400", bgColor: "bg-amber-500/12" },
  ];

  const quickActions = [
    { titleKey: "access.add_user", descKey: "access.add_user_desc", icon: UserCheck, url: "/settings/users?action=create" },
    { titleKey: "access.configure_roles", descKey: "access.configure_roles_desc", icon: KeyRound, url: "/settings/groups" },
  ];
  return (
    <div className="space-y-6 pb-10">
      {/* Header */}
      <div className="flex items-center gap-3">
        <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-primary/10">
          <Lock className="h-4 w-4 text-primary" />
        </div>
        <div>
          <h1 className="text-base font-semibold tracking-tight text-foreground">Управление доступом</h1>
          <p className="text-[11px] text-muted-foreground">Пользователи, группы и точечные разрешения</p>
        </div>
      </div>

      {/* Info */}
      <div className="rounded-xl border border-border/60 bg-secondary/10 px-5 py-4">
        <p className="text-sm leading-relaxed text-muted-foreground/70">
          Базовую модель прав рекомендуется строить через <strong className="text-foreground/80 font-medium">профили</strong> и <strong className="text-foreground/80 font-medium">группы</strong>.
          Раздел <strong className="text-foreground/80 font-medium">разрешений</strong> используйте только при необходимости точечного исключения.
        </p>
      </div>

      {/* Navigation cards */}
      <div className="overflow-hidden rounded-xl border border-border bg-card shadow-sm">
        {accessPages.map((page, index, pages) => (
          <Link
            key={page.url}
            to={page.url}
            className={cn(
              "group flex items-center gap-4 px-5 py-4 transition-all duration-150 hover:bg-secondary/25",
              index < pages.length - 1 && "border-b border-border/50"
            )}
          >
            <div className={cn("flex h-10 w-10 shrink-0 items-center justify-center rounded-xl transition-all duration-150 group-hover:scale-105", page.bgColor)}>
              <page.icon className={cn("h-4.5 w-4.5", page.color)} aria-hidden="true" />
            </div>
            <div className="min-w-0 flex-1">
              <p className="text-sm font-semibold text-foreground transition-colors">{t(page.titleKey)}</p>
              <p className="mt-0.5 text-[11px] text-muted-foreground">{t(page.descKey)}</p>
            </div>
            <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg text-muted-foreground/40 transition-all duration-150 group-hover:bg-secondary/50 group-hover:text-foreground/60 group-hover:translate-x-0.5">
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
              className="group flex items-center gap-3 rounded-xl border border-border/60 bg-card px-4 py-3.5 shadow-sm transition-all duration-150 hover:bg-secondary/25 hover:shadow-md"
            >
              <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary transition-colors duration-200 group-hover:bg-primary group-hover:text-primary-foreground">
                <action.icon className="h-4 w-4" />
              </div>
              <div className="min-w-0 flex-1">
                <p className="text-sm font-medium text-foreground/90">{t(action.titleKey)}</p>
                <p className="text-[11px] text-muted-foreground/50">{t(action.descKey)}</p>
              </div>
            </Link>
          ))}
        </div>
      </div>

      {/* How it works */}
      <div className="rounded-xl border border-dashed border-border/50 bg-secondary/10 px-5 py-5">
        <h3 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground flex items-center gap-2">
          <div className="h-1.5 w-1.5 rounded-full bg-primary/60" />
          Как работает система доступа
        </h3>
        <div className="mt-4 space-y-3 text-[13px] text-muted-foreground/70">
          <p className="flex items-start gap-2.5">
            <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-md bg-secondary text-[10px] font-bold text-muted-foreground mt-px">1</span>
            <span><strong className="text-foreground/70 font-medium">Пользователи</strong> — создавайте аккаунты и назначайте профили доступа.</span>
          </p>
          <p className="flex items-start gap-2.5">
            <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-md bg-secondary text-[10px] font-bold text-muted-foreground mt-px">2</span>
            <span><strong className="text-foreground/70 font-medium">Группы</strong> — объединяйте пользователей с одинаковыми правами.</span>
          </p>
          <p className="flex items-start gap-2.5">
            <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-md bg-secondary text-[10px] font-bold text-muted-foreground mt-px">3</span>
            <span><strong className="text-foreground/70 font-medium">Разрешения</strong> — настраивайте точечные исключения при необходимости.</span>
          </p>
        </div>
      </div>
    </div>
  );
}
