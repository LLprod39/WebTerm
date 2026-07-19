import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { localize, useI18n } from "@/lib/i18n";

type Props = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
};

type Row = { keys: string; ru: string; en: string };

const ROWS: Row[] = [
  { keys: "Ctrl/⌘ K", ru: "Командная палитра", en: "Command palette" },
  { keys: "Ctrl/⌘ .", ru: "Ассистент (слайд-овер)", en: "Assistant slide-over" },
  { keys: "g d", ru: "Дашборд", en: "Dashboard" },
  { keys: "g s", ru: "Серверы", en: "Servers" },
  { keys: "g a", ru: "Агенты", en: "Agents" },
  { keys: "g c", ru: "Чат", en: "Chat page" },
  { keys: "g m", ru: "Insights / мониторинг", en: "Monitoring insights" },
  { keys: "g k", ru: "Kubernetes", en: "Kubernetes" },
  { keys: "g t", ru: "Studio", en: "Studio" },
  { keys: "?", ru: "Эта шпаргалка", en: "This cheatsheet" },
  { keys: "Esc", ru: "Закрыть оверлей", en: "Close overlay" },
];

export function HotkeyCheatsheet({ open, onOpenChange }: Props) {
  const { lang } = useI18n();

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md gap-0 overflow-hidden p-0">
        <DialogHeader className="border-b border-border px-5 py-4">
          <DialogTitle className="text-base font-semibold">
            {localize(lang, "Горячие клавиши", "Keyboard shortcuts")}
          </DialogTitle>
        </DialogHeader>
        <ul className="max-h-[min(70vh,420px)] overflow-y-auto px-2 py-2">
          {ROWS.map((row) => (
            <li
              key={row.keys}
              className="flex items-center justify-between gap-4 rounded-md px-3 py-2.5 text-sm hover:bg-secondary/50"
            >
              <span className="text-foreground">{localize(lang, row.ru, row.en)}</span>
              <kbd className="shrink-0 rounded border border-border bg-surface-1 px-2 py-0.5 font-mono text-[11px] text-muted-foreground">
                {row.keys}
              </kbd>
            </li>
          ))}
        </ul>
      </DialogContent>
    </Dialog>
  );
}
