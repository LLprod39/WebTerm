import { useRef, useState, type ReactNode } from "react";
import { useQueryClient } from "@tanstack/react-query";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Feedback, StatusBadge } from "@/components/ui";
import type { Details } from "@/api/intelligence";
export const activeRun = (status?: string) =>
  !!status &&
  ["pending", "queued", "running", "paused", "waiting", "plan_review"].includes(
    status,
  );
export function text(value: unknown, fallback = "—"): string {
  if (typeof value === "string" || typeof value === "number")
    return String(value);
  return fallback;
}
export function record(value: unknown): Details {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Details)
    : {};
}
export function list(value: unknown): Details[] {
  return Array.isArray(value) ? value.map(record) : [];
}
export function Markdown({ children }: { children?: string | null }) {
  return (
    <div className="intel-markdown">
      <ReactMarkdown remarkPlugins={[remarkGfm]}>
        {children || ""}
      </ReactMarkdown>
    </div>
  );
}
const statusLabels: Record<string, string> = {
  mini: "Командный",
  full: "Автономный",
  multi: "Командная работа",
  waiting: "Нужен ответ",
  plan_review: "На согласовании",
  paused: "Приостановлено",
  stopped: "Остановлено",
  interview: "Уточнение задачи",
  plan_ready: "План готов",
  awaiting_confirm: "Нужно подтверждение",
  requires_confirmation: "Нужно подтверждение",
  done: "Завершено",
  canceled: "Отменено",
  manual: "Вручную",
  canonical: "Проверенные сведения",
  pattern: "Повторяющийся сценарий",
  automation: "Кандидат автоматизации",
  skill_draft: "Черновик навыка",
  manual_note: "Заметка",
  ai_note: "Заметка AI",
  untested: "Не проверено",
};
export function IntelStatus({ value }: { value: string }) {
  return (
    <StatusBadge status={value}>{statusLabels[value] || undefined}</StatusBadge>
  );
}
export function useOperation() {
  const lock = useRef(false);
  const [error, setError] = useState<unknown>();
  const [success, setSuccess] = useState("");
  const [pending, setPending] = useState(false);
  const client = useQueryClient();
  const run = async <T,>(
    action: () => Promise<T>,
    message = "",
    onSuccess?: (result: T) => void,
  ) => {
    if (lock.current) return;
    lock.current = true;
    setPending(true);
    setError(undefined);
    setSuccess("");
    try {
      const result = await action();
      setSuccess(message);
      onSuccess?.(result);
      await client.invalidateQueries({ queryKey: ["intelligence"] });
      return result;
    } catch (cause) {
      setError(cause);
    } finally {
      lock.current = false;
      setPending(false);
    }
  };
  return {
    run,
    pending,
    error,
    feedback: <Feedback error={error} success={success} />,
  };
}
export function DetailRows({
  items,
}: {
  items: { label: string; value: ReactNode }[];
}) {
  return (
    <dl className="intel-details">
      {items.map((item) => (
        <div key={item.label}>
          <dt>{item.label}</dt>
          <dd>{item.value}</dd>
        </div>
      ))}
    </dl>
  );
}
export function DetailCards({
  items,
  empty = "Данных пока нет",
}: {
  items: Details[];
  empty?: string;
}) {
  return items.length ? (
    <div className="intel-evidence-list">
      {items.map((item, i) => (
        <article className="intel-evidence" key={text(item.id, String(i))}>
          <div className="intel-row">
            <strong>
              {text(
                item.title || item.name || item.label || item.event_type,
                "Событие",
              )}
            </strong>
            {item.status != null && <IntelStatus value={text(item.status)} />}
          </div>
          <p>
            {text(
              item.summary ||
                item.description ||
                item.message ||
                item.content ||
                item.result,
              "",
            )}
          </p>
          {item.created_at != null && (
            <small className="muted">{text(item.created_at)}</small>
          )}
          {item.download_url != null && (
            <a className="text-link" href={text(item.download_url)}>
              Скачать
            </a>
          )}
        </article>
      ))}
    </div>
  ) : (
    <p className="muted intel-pad">{empty}</p>
  );
}
