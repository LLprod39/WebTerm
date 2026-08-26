import { useMemo } from "react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import {
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  FolderOpen,
  KeyRound,
  Lock,
  Shield,
  UserPlus,
  Users,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  fetchAccessGroupPermissions,
  fetchAccessGroups,
  fetchAccessPermissions,
  fetchAccessUsers,
} from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { cn } from "@/lib/utils";

type Tone = "neutral" | "success" | "warning" | "danger" | "info";

const toneClasses: Record<Tone, string> = {
  neutral: "border-border/70 bg-secondary/10 text-muted-foreground",
  success: "border-emerald-500/25 bg-emerald-500/10 text-emerald-300",
  warning: "border-amber-500/25 bg-amber-500/10 text-amber-300",
  danger: "border-red-500/25 bg-red-500/10 text-red-300",
  info: "border-blue-500/25 bg-blue-500/10 text-blue-300",
};

function MetricTile({
  label,
  value,
  tone = "neutral",
}: {
  label: string;
  value: number | string;
  tone?: Tone;
}) {
  return (
    <div className={cn("rounded-lg border px-4 py-3", toneClasses[tone])}>
      <div className="text-2xl font-semibold leading-8 text-foreground">{value}</div>
      <div className="mt-1 text-sm leading-5">{label}</div>
    </div>
  );
}

function RiskRow({
  label,
  detail,
  value,
  tone,
  href,
}: {
  label: string;
  detail: string;
  value: number;
  tone: Tone;
  href: string;
}) {
  const ok = value === 0;
  return (
    <Link
      to={href}
      className="group flex items-center gap-3 border-b border-border/50 px-4 py-3 last:border-b-0 hover:bg-secondary/20"
    >
      <div
        className={cn(
          "flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border",
          ok ? toneClasses.success : toneClasses[tone],
        )}
      >
        {ok ? <CheckCircle2 className="h-4 w-4" /> : <AlertTriangle className="h-4 w-4" />}
      </div>
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-sm font-semibold text-foreground">{label}</span>
          <span className={cn("rounded-md border px-1.5 py-0.5 text-xs font-medium", ok ? toneClasses.success : toneClasses[tone])}>
            {value}
          </span>
        </div>
        <p className="mt-0.5 text-sm leading-5 text-muted-foreground">{detail}</p>
      </div>
      <ArrowRight className="h-4 w-4 shrink-0 text-muted-foreground/50 transition-transform group-hover:translate-x-0.5 group-hover:text-foreground" />
    </Link>
  );
}

function NavRow({
  title,
  description,
  href,
  icon: Icon,
}: {
  title: string;
  description: string;
  href: string;
  icon: typeof Users;
}) {
  return (
    <Link
      to={href}
      className="group flex min-h-16 items-center gap-3 border-b border-border/50 px-4 py-3 last:border-b-0 hover:bg-secondary/20"
    >
      <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border border-border/70 bg-secondary/20 text-primary">
        <Icon className="h-4 w-4" />
      </div>
      <div className="min-w-0 flex-1">
        <p className="text-sm font-semibold text-foreground">{title}</p>
        <p className="mt-0.5 text-sm leading-5 text-muted-foreground">{description}</p>
      </div>
      <ArrowRight className="h-4 w-4 shrink-0 text-muted-foreground/50 transition-transform group-hover:translate-x-0.5 group-hover:text-foreground" />
    </Link>
  );
}

export default function SettingsAccessPage() {
  const { lang } = useI18n();
  const tr = (ru: string, en: string) => (lang === "ru" ? ru : en);

  const usersQuery = useQuery({ queryKey: ["access", "users"], queryFn: fetchAccessUsers });
  const groupsQuery = useQuery({ queryKey: ["access", "groups"], queryFn: fetchAccessGroups });
  const permissionsQuery = useQuery({ queryKey: ["access", "permissions"], queryFn: fetchAccessPermissions });
  const groupPermissionsQuery = useQuery({
    queryKey: ["access", "group-permissions"],
    queryFn: fetchAccessGroupPermissions,
  });

  const users = useMemo(() => usersQuery.data?.users ?? [], [usersQuery.data?.users]);
  const groups = useMemo(() => groupsQuery.data?.groups ?? [], [groupsQuery.data?.groups]);
  const directPermissions = useMemo(() => permissionsQuery.data?.permissions ?? [], [permissionsQuery.data?.permissions]);
  const groupPermissions = useMemo(
    () => groupPermissionsQuery.data?.permissions ?? permissionsQuery.data?.group_permissions ?? [],
    [groupPermissionsQuery.data?.permissions, permissionsQuery.data?.group_permissions],
  );
  const isLoading = usersQuery.isLoading || groupsQuery.isLoading || permissionsQuery.isLoading || groupPermissionsQuery.isLoading;
  const isError = usersQuery.isError || groupsQuery.isError || permissionsQuery.isError || groupPermissionsQuery.isError;

  const metrics = useMemo(() => {
    const activeUsers = users.filter((user) => user.is_active).length;
    const admins = users.filter((user) => user.is_staff || user.is_superuser).length;
    const inactiveWithAccess = users.filter((user) => {
      if (user.is_active) return false;
      return Object.values(user.effective_permissions || {}).some(Boolean);
    }).length;
    const usersWithoutGroup = users.filter((user) => user.is_active && (user.groups || []).length === 0).length;
    const directOverrideUsers = new Set(directPermissions.map((permission) => permission.user_id)).size;
    const deniedOverrides =
      directPermissions.filter((permission) => !permission.allowed).length +
      groupPermissions.filter((permission) => !permission.allowed).length;

    return {
      activeUsers,
      admins,
      inactiveWithAccess,
      usersWithoutGroup,
      directOverrideUsers,
      deniedOverrides,
      totalOverrides: directPermissions.length + groupPermissions.length,
    };
  }, [directPermissions, groupPermissions, users]);

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-20">
        <div className="h-6 w-6 animate-spin rounded-full border-2 border-primary border-t-transparent" />
      </div>
    );
  }

  if (isError) {
    return (
      <div className="rounded-xl border border-red-500/30 bg-red-500/10 px-5 py-4 text-sm text-red-100">
        {tr("Не удалось загрузить сводку доступа.", "Could not load the access summary.")}
      </div>
    );
  }

  return (
    <div className="space-y-6 pb-10">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-primary/10">
            <Lock className="h-4 w-4 text-primary" />
          </div>
          <div>
            <h1 className="text-xl font-semibold tracking-tight text-foreground">
              {tr("Доступ", "Access Control")}
            </h1>
            <p className="mt-1 text-sm leading-5 text-muted-foreground">
              {tr(
                "Пользователи, группы и точечные исключения.",
                "Summary of users, groups, and explicit access exceptions.",
              )}
            </p>
          </div>
        </div>
        <Button asChild className="h-10 gap-2">
          <Link to="/settings/users?action=create">
            <UserPlus className="h-4 w-4" />
            {tr("Добавить пользователя", "Add user")}
          </Link>
        </Button>
      </div>

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <MetricTile label={tr("активных пользователей", "active users")} value={metrics.activeUsers} tone="success" />
        <MetricTile label={tr("администраторов", "admins")} value={metrics.admins} tone={metrics.admins ? "info" : "warning"} />
        <MetricTile label={tr("групп доступа", "access groups")} value={groups.length} />
        <MetricTile
          label={tr("точечных исключений", "explicit exceptions")}
          value={metrics.totalOverrides}
          tone={metrics.totalOverrides ? "warning" : "success"}
        />
      </div>

      <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_360px]">
        <section className="overflow-hidden rounded-xl border border-border bg-card">
          <div className="border-b border-border/60 px-4 py-3">
            <h2 className="text-base font-semibold text-foreground">{tr("Риски доступа", "Access Risks")}</h2>
            <p className="mt-1 text-sm text-muted-foreground">
              {tr("Проверьте перед изменением правил.", "Review before changing policy.")}
            </p>
          </div>
          <RiskRow
            href="/settings/users"
            label={tr("Отключённые аккаунты с доступом", "Inactive accounts with access")}
            detail={tr("Аккаунт отключён, но у пользователя остались разрешения.", "The account is disabled but still has permissions.")}
            value={metrics.inactiveWithAccess}
            tone="danger"
          />
          <RiskRow
            href="/settings/users"
            label={tr("Пользователи без группы", "Users without a group")}
            detail={tr("Права таких пользователей сложнее поддерживать централизованно.", "These users are harder to manage centrally.")}
            value={metrics.usersWithoutGroup}
            tone="warning"
          />
          <RiskRow
            href="/settings/permissions"
            label={tr("Пользователи с прямыми исключениями", "Users with direct exceptions")}
            detail={tr("Прямые исключения должны быть временными и понятными.", "Direct exceptions should be temporary and explainable.")}
            value={metrics.directOverrideUsers}
            tone="warning"
          />
          <RiskRow
            href="/settings/permissions"
            label={tr("Запреты-исключения", "Deny exceptions")}
            detail={tr("Запреты могут перекрывать ожидаемые права профиля или группы.", "Denies can override expected profile or group access.")}
            value={metrics.deniedOverrides}
            tone="info"
          />
        </section>

        <section className="overflow-hidden rounded-xl border border-border bg-card">
          <div className="border-b border-border/60 px-4 py-3">
            <h2 className="text-base font-semibold text-foreground">{tr("Разделы", "Sections")}</h2>
          </div>
          <NavRow
            href="/settings/users"
            icon={Users}
            title={tr("Пользователи", "Users")}
            description={tr("Аккаунты, профили, группы и смена пароля.", "Accounts, profiles, groups, and password reset.")}
          />
          <NavRow
            href="/settings/groups"
            icon={FolderOpen}
            title={tr("Группы", "Groups")}
            description={tr("Команды, участники и наследуемые групповые правила.", "Teams, members, and inherited group policy.")}
          />
          <NavRow
            href="/settings/permissions"
            icon={Shield}
            title={tr("Разрешения", "Permissions")}
            description={tr("Итоговые права и точечные разрешения или запреты.", "Effective access and explicit allow or deny exceptions.")}
          />
          <div className="border-t border-border/60 px-4 py-3 text-sm leading-6 text-muted-foreground">
            <KeyRound className="mr-2 inline h-4 w-4 text-primary" />
            {tr(
              "Базовую модель держите в профилях и группах, а исключения используйте только для точечных случаев.",
              "Keep the baseline in profiles and groups; use exceptions only for specific cases.",
            )}
          </div>
        </section>
      </div>
    </div>
  );
}
