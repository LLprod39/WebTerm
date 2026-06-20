import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  ArrowLeft,
  ChevronRight,
  Download,
  Share2,
  MoreVertical,
  Menu,
  CheckCircle2,
  Printer,
  Link2,
  RefreshCw,
} from "lucide-react";
import { toast } from "sonner";

interface TopBarProps {
  onOpenMobileNav: () => void;
}

const crumbs = ["Агенты", "Запуски", "Анализ логов"];

export function TopBar({ onOpenMobileNav }: TopBarProps) {
  return (
    <header className="sticky top-0 z-30 border-b border-border bg-surface/95 backdrop-blur supports-[backdrop-filter]:bg-surface/80">
      <div className="flex h-16 items-center gap-3 px-4 sm:px-6">
        <Button
          variant="ghost"
          size="icon"
          className="lg:hidden"
          aria-label="Открыть меню"
          onClick={onOpenMobileNav}
        >
          <Menu className="h-5 w-5" />
        </Button>

        <Button variant="outline" size="sm" className="h-10 gap-1.5" onClick={() => toast("Возврат к списку запусков")}>
          <ArrowLeft className="h-4 w-4" />
          <span className="hidden sm:inline">Назад</span>
        </Button>

        <nav aria-label="Хлебные крошки" className="hidden min-w-0 items-center gap-1.5 md:flex">
          {crumbs.map((c, i) => (
            <span key={c} className="flex items-center gap-1.5">
              {i > 0 && <ChevronRight className="h-3.5 w-3.5 text-muted-foreground" />}
              <span
                className={
                  i === crumbs.length - 1
                    ? "text-sm font-medium text-foreground"
                    : "text-sm text-muted-foreground"
                }
              >
                {c}
              </span>
            </span>
          ))}
        </nav>

        <div className="ml-auto flex items-center gap-2">
          <span className="hidden items-center gap-1.5 rounded-md border border-success/30 bg-success/15 px-2.5 py-1.5 text-xs font-medium text-success sm:inline-flex">
            <CheckCircle2 className="h-3.5 w-3.5" />
            Завершён
          </span>

          <Button
            size="sm"
            className="h-10 gap-1.5"
            onClick={() => toast.success("Скачивание report.pdf начато", { description: "128 KB" })}
          >
            <Download className="h-4 w-4" />
            <span className="hidden sm:inline">Скачать PDF</span>
          </Button>

          <Button
            variant="outline"
            size="sm"
            className="h-10 gap-1.5"
            onClick={() => {
              toast.success("Ссылка на отчёт скопирована");
            }}
          >
            <Share2 className="h-4 w-4" />
            <span className="hidden md:inline">Поделиться</span>
          </Button>

          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="ghost" size="icon" className="h-10 w-10" aria-label="Действия">
                <MoreVertical className="h-5 w-5" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="w-52">
              <DropdownMenuItem onClick={() => toast("Открыто окно печати")}>
                <Printer className="mr-2 h-4 w-4" /> Печать отчёта
              </DropdownMenuItem>
              <DropdownMenuItem onClick={() => toast.success("Постоянная ссылка скопирована")}>
                <Link2 className="mr-2 h-4 w-4" /> Постоянная ссылка
              </DropdownMenuItem>
              <DropdownMenuSeparator />
              <DropdownMenuItem onClick={() => toast("Запущен повторный анализ")}>
                <RefreshCw className="mr-2 h-4 w-4" /> Перезапустить анализ
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      </div>
    </header>
  );
}
