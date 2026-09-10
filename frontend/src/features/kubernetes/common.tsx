import { useEffect, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { NavLink } from "react-router-dom";
import { Feedback, StatusBadge, DataTable } from "@/components/ui";
import { useSession } from "@/app/session";
import { formatDate } from "@/lib/utils";
import {
  kubernetesApi,
  type KubeData,
  type KubeSession,
} from "@/api/kubernetes";
export const kubeBase = "/infrastructure/kubernetes";
export const obj = (v: unknown): KubeData =>
  v && typeof v === "object" && !Array.isArray(v) ? (v as KubeData) : {};
export const rows = (v: unknown): KubeData[] =>
  Array.isArray(v)
    ? (v.filter((x) => x && typeof x === "object") as KubeData[])
    : [];
export const str = (v: unknown, fallback = "—"): string =>
  v === null || v === undefined || v === ""
    ? fallback
    : typeof v === "string"
      ? v
      : typeof v === "object"
        ? JSON.stringify(v)
        : String(v);
export function KubeNav() {
  const { user } = useSession();
  return (
    <nav className="kube-nav" aria-label="Разделы Kubernetes">
      <NavLink to={kubeBase} end>
        Кластеры
      </NavLink>
      <NavLink to={`${kubeBase}/delivery`}>Поставки</NavLink>
      <NavLink to={`${kubeBase}/requests`}>Заявки</NavLink>
      <NavLink to={`${kubeBase}/sessions`}>Сессии доступа</NavLink>
      <NavLink to={`${kubeBase}/activity`}>Действия и записи</NavLink>
      <NavLink to={`${kubeBase}/readiness`}>Готовность</NavLink>
      {user?.is_staff && (
        <NavLink to={`${kubeBase}/providers`}>Провайдеры</NavLink>
      )}
    </nav>
  );
}
export function KubeStatus({ value }: { value: unknown }) {
  const s = str(value, "unknown");
  const labels: Record<string, string> = {
    approved_external: "Согласована",
    executed_native: "Выполнена",
    verified_external: "Подтверждена внешне",
    verified_native: "Проверена",
    verification_failed: "Проверка не пройдена",
    connecting: "Подключение",
    connected: "Подключено",
    disconnected: "Отключено",
    reconnecting: "Восстановление",
    healthy: "В норме",
    ready: "Готово",
    active: "Активна",
    pending_approval: "На согласовании",
    closed: "Закрыта",
    expired: "Истекла",
    revoked: "Отозвана",
    degraded: "Деградация",
    warning: "Внимание",
    unknown: "Неизвестно",
    missing: "Не настроено",
    not_configured: "Не настроено",
    configured: "Настроено",
    completed: "Завершено",
    failed: "Ошибка",
    execution_blocked: "Выполнение запрещено",
    dry_run: "Проверено без изменений",
    fresh: "Актуально",
    stale: "Устарело",
    error: "Ошибка",
    pending: "Ожидает",
    Running: "Работает",
    Succeeded: "Завершено",
    Failed: "Ошибка",
  };
  return <StatusBadge status={s}>{labels[s] || s}</StatusBadge>;
}
export function useKubeOperation() {
  const cache = useQueryClient();
  const lock = useRef(false);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<unknown>();
  const [success, setSuccess] = useState("");
  async function run<T>(fn: () => Promise<T>, message = "Изменения сохранены") {
    if (lock.current) return;
    lock.current = true;
    setPending(true);
    setError(undefined);
    setSuccess("");
    try {
      const result = await fn();
      setSuccess(message);
      await cache.invalidateQueries({ queryKey: ["kubernetes"] });
      return result;
    } catch (e) {
      setError(e);
      return undefined;
    } finally {
      lock.current = false;
      setPending(false);
    }
  }
  return {
    run,
    pending,
    error,
    feedback: <Feedback error={error} success={success} />,
  };
}
export function useKubeCapabilities() {
  return useQuery({
    queryKey: ["kubernetes", "capabilities"],
    queryFn: kubernetesApi.capabilities,
    staleTime: 30_000,
  });
}
export function useActiveKubeSession(session: KubeSession) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, []);
  return (
    session.status === "active" && new Date(session.expires_at).getTime() > now
  );
}
export function KubeFacts({
  data,
  fields,
}: {
  data: KubeData;
  fields: [string, string][];
}) {
  return (
    <dl className="detail-list">
      {fields.map(([key, label]) => (
        <div key={key}>
          <dt>{label}</dt>
          <dd>{str(data[key])}</dd>
        </div>
      ))}
    </dl>
  );
}
export function KubeEvents({ events }: { events: KubeData[] }) {
  return (
    <DataTable
      rows={events}
      rowKey={(r) =>
        str(r.id, str(r.reason) + str(r.last_seen) + str(r.message))
      }
      searchValue={(r) =>
        `${str(r.reason)} ${str(r.message)} ${str(r.object_name)}`
      }
      emptyTitle="Событий нет"
      columns={[
        {
          key: "reason",
          label: "Событие",
          render: (r) => (
            <>
              <strong>
                {str(r.reason, r.action ? str(r.action) : "Событие")}
              </strong>
              <p className="muted">
                {str(r.message, r.summary ? str(r.summary) : "")}
              </p>
            </>
          ),
        },
        {
          key: "object",
          label: "Объект",
          render: (r) =>
            str(
              r.object_name,
              r.involved_object ? str(r.involved_object) : str(r.namespace),
            ),
        },
        {
          key: "status",
          label: "Уровень",
          render: (r) => (
            <KubeStatus value={r.type || r.severity || r.status} />
          ),
        },
        {
          key: "date",
          label: "Время",
          render: (r) =>
            formatDate(
              str(
                r.last_timestamp || r.last_seen || r.created_at || r.timestamp,
                "",
              ),
            ),
        },
      ]}
    />
  );
}
