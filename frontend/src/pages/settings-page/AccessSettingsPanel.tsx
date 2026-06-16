import { Link } from "react-router-dom";
import { ChevronRight, FolderOpen, Shield, Users } from "lucide-react";
import { cn } from "@/lib/utils";
import { SectionCard } from "./SectionCard";

const ACCESS_PAGES = [
  { title: "Пользователи", desc: "Аккаунты, профили доступа и группы пользователя", icon: Users, url: "/settings/users" },
  { title: "Группы", desc: "Команды, участники и общая политика доступа", icon: FolderOpen, url: "/settings/groups" },
  { title: "Разрешения", desc: "Точечные allow/deny правила для исключений", icon: Shield, url: "/settings/permissions" },
];

export function AccessSettingsPanel() {
  return (
    <SectionCard title="Настройки доступа" icon={Shield} description="Три понятных шага: пользователи, группы, затем точечные исключения.">
      <div className="workspace-subtle rounded-xl px-4 py-3 text-sm leading-6 text-muted-foreground">
        Базовую модель прав лучше собирать через профили и группы. Раздел разрешений используй только там, где действительно нужно сделать исключение.
      </div>

      <div className="mt-4 overflow-hidden rounded-xl border border-border/70">
        {ACCESS_PAGES.map((page, index, pages) => (
          <Link
            key={page.url}
            to={page.url}
            className={cn(
              "group flex items-center gap-4 bg-card px-4 py-4 transition-colors hover:bg-secondary/30",
              index < pages.length - 1 && "border-b border-border/70",
            )}
          >
            <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg border border-border/70 bg-background">
              <page.icon className="h-4 w-4 text-muted-foreground" aria-hidden="true" />
            </div>
            <div className="min-w-0 flex-1">
              <p className="text-sm font-medium text-foreground">{page.title}</p>
              <p className="mt-0.5 text-sm text-muted-foreground">{page.desc}</p>
            </div>
            <ChevronRight className="h-4 w-4 shrink-0 text-muted-foreground transition-colors group-hover:text-foreground" aria-hidden="true" />
          </Link>
        ))}
      </div>
    </SectionCard>
  );
}
