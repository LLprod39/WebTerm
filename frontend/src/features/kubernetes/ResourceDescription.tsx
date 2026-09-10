import { useQuery } from "@tanstack/react-query";
import {
  Button,
  DataTable,
  EmptyState,
  ErrorState,
  LoadingState,
  Panel,
} from "@/components/ui";
import {
  describeResource,
  type DescribeAvailability,
  type ResourceOwner,
} from "@/api/kubernetes-describe";
import type { KubeSession, ResourceTarget } from "@/api/kubernetes";
import { formatDate } from "@/lib/utils";
import { KubeEvents, KubeStatus, str, useActiveKubeSession } from "./common";

const skippedReasons: Record<string, string> = {
  no_pod_selector:
    "У ресурса нет селектора Pods или пространства имён для поиска.",
  no_controller_context:
    "Для этого типа ресурса связанные контроллеры не предоставляются.",
  no_controller_selector: "У ресурса нет селектора связанных контроллеров.",
  selector_contains_sensitive_key:
    "Поиск по этому селектору скрыт политикой защиты данных.",
};

function Unavailable({ section }: { section: DescribeAvailability }) {
  const reason = section.skipped_reason;
  return (
    <EmptyState
      title="Данные недоступны"
      description={
        section.error?.message ||
        (reason && skippedReasons[reason]) ||
        (reason
          ? `Получение данных ограничено: ${reason}.`
          : "Провайдер не вернул данные для этой области.")
      }
    />
  );
}

function Owners({ owners }: { owners: ResourceOwner[] }) {
  return (
    <DataTable
      rows={owners}
      rowKey={(owner) => `${owner.api_version}/${owner.kind}/${owner.name}`}
      emptyTitle="Владелец не указан"
      columns={[
        { key: "name", label: "Объект", render: (owner) => owner.name },
        { key: "kind", label: "Тип", render: (owner) => owner.kind },
        { key: "version", label: "API", render: (owner) => owner.api_version },
        {
          key: "controller",
          label: "Управляет ресурсом",
          render: (owner) => (owner.controller ? "Да" : "Нет"),
        },
      ]}
    />
  );
}

export function ResourceDescription({
  session,
  target,
}: {
  session: KubeSession;
  target: ResourceTarget;
}) {
  const active = useActiveKubeSession(session);
  const query = useQuery({
    queryKey: ["kubernetes", "live-description", session.id, target],
    queryFn: () => describeResource(session.cluster_id, session.id, target),
    enabled: active,
  });
  if (!active)
    return (
      <EmptyState
        title="Сессия доступа завершена"
        description="Для получения актуального описания откройте новую сессию."
      />
    );
  if (query.isPending)
    return <LoadingState label="Получаем описание и связанные ресурсы…" />;
  if (query.error)
    return <ErrorState error={query.error} retry={() => query.refetch()} />;
  if (!query.data) return <EmptyState title="Описание ресурса отсутствует" />;
  const { summary, related, events, provider } = query.data;
  const { identity, metadata, spec, status } = summary;
  return (
    <div className="stack">
      <div className="spread">
        <p className="muted">
          Источник: {provider.name} · получено{" "}
          {formatDate(new Date(query.dataUpdatedAt).toISOString())}
        </p>
        <Button onClick={() => query.refetch()} loading={query.isFetching}>
          Обновить описание
        </Button>
      </div>
      {query.data.redacted && (
        <p className="notice">Часть сведений скрыта политикой защиты данных.</p>
      )}
      <Panel title="Состояние ресурса">
        <div className="section-body stack">
          <dl className="detail-list">
            <div>
              <dt>API и тип</dt>
              <dd>
                {identity.api_version} · {identity.kind}
              </dd>
            </div>
            <div>
              <dt>Пространство имён</dt>
              <dd>{identity.namespace || "Уровень кластера"}</dd>
            </div>
            <div>
              <dt>Версия ресурса</dt>
              <dd>{str(identity.resource_version)}</dd>
            </div>
            <div>
              <dt>Поколение / наблюдаемое</dt>
              <dd>
                {str(identity.generation)} / {str(status.observed_generation)}
              </dd>
            </div>
            <div>
              <dt>Создан</dt>
              <dd>{formatDate(identity.creation_timestamp)}</dd>
            </div>
            <div>
              <dt>UID</dt>
              <dd className="mono">{str(identity.uid)}</dd>
            </div>
            {status.phase && (
              <div>
                <dt>Фаза</dt>
                <dd>
                  <KubeStatus value={status.phase} />
                </dd>
              </div>
            )}
            {spec.replicas != null && (
              <div>
                <dt>Желаемых / готовых реплик</dt>
                <dd>
                  {spec.replicas} / {str(status.ready_replicas)}
                </dd>
              </div>
            )}
            {status.replicas != null && (
              <div>
                <dt>Всего / обновлённых / доступных</dt>
                <dd>
                  {status.replicas} / {str(status.updated_replicas)} /{" "}
                  {str(status.available_replicas)}
                </dd>
              </div>
            )}
            {spec.strategy && (
              <div>
                <dt>Стратегия</dt>
                <dd>{spec.strategy}</dd>
              </div>
            )}
            {spec.service_type && (
              <div>
                <dt>Тип Service</dt>
                <dd>{spec.service_type}</dd>
              </div>
            )}
            {spec.container_count > 0 && (
              <div>
                <dt>Контейнеры ({spec.container_count})</dt>
                <dd>{spec.container_names.join(", ")}</dd>
              </div>
            )}
          </dl>
          {(status.reason || status.message) && (
            <p className="notice">
              {[status.reason, status.message].filter(Boolean).join(": ")}
            </p>
          )}
        </div>
        <DataTable
          rows={status.conditions}
          rowKey={(condition) =>
            `${condition.type}/${condition.last_transition_time}`
          }
          emptyTitle="Условия состояния отсутствуют"
          columns={[
            {
              key: "type",
              label: "Условие",
              render: (condition) => condition.type,
            },
            {
              key: "status",
              label: "Значение",
              render: (condition) => str(condition.status),
            },
            {
              key: "reason",
              label: "Причина",
              render: (condition) => (
                <>
                  <strong>{str(condition.reason)}</strong>
                  <p className="muted">{condition.message}</p>
                </>
              ),
            },
            {
              key: "time",
              label: "Изменено",
              render: (condition) => formatDate(condition.last_transition_time),
            },
          ]}
        />
        {status.conditions_truncated && (
          <p className="section-body muted">
            Показаны первые 12 условий состояния.
          </p>
        )}
      </Panel>
      <Panel title="Метаданные и владельцы">
        <dl className="detail-list section-body">
          <div>
            <dt>Ключи меток</dt>
            <dd>{metadata.label_keys.join(", ") || "Нет"}</dd>
          </div>
          <div>
            <dt>Ключи аннотаций</dt>
            <dd>{metadata.annotation_keys.join(", ") || "Нет"}</dd>
          </div>
          <div>
            <dt>Ключи селектора</dt>
            <dd>{spec.selector_keys.join(", ") || "Нет"}</dd>
          </div>
        </dl>
        <Owners owners={metadata.owner_references} />
      </Panel>
      {spec.ports.length > 0 && (
        <Panel title="Порты Service">
          <DataTable
            rows={spec.ports}
            rowKey={(port) => `${port.name}/${port.protocol}/${port.port}`}
            columns={[
              { key: "name", label: "Имя", render: (port) => str(port.name) },
              { key: "port", label: "Порт", render: (port) => str(port.port) },
              {
                key: "target",
                label: "Целевой порт",
                render: (port) => str(port.target_port),
              },
              {
                key: "protocol",
                label: "Протокол",
                render: (port) => str(port.protocol),
              },
            ]}
          />
        </Panel>
      )}
      <Panel
        title="Связанные Pods"
        description="Pods, соответствующие селектору в разрешённой области сессии."
      >
        {!related.pods.available ? (
          <Unavailable section={related.pods} />
        ) : (
          <>
            <DataTable
              rows={related.pods.items}
              rowKey={(pod) => `${pod.namespace}/${pod.name}`}
              emptyTitle="Подходящих Pods не найдено"
              columns={[
                {
                  key: "name",
                  label: "Pod",
                  render: (pod) => (
                    <>
                      <strong>{pod.name}</strong>
                      <p className="muted">{pod.namespace}</p>
                    </>
                  ),
                },
                {
                  key: "phase",
                  label: "Фаза",
                  render: (pod) => <KubeStatus value={pod.phase} />,
                },
                {
                  key: "ready",
                  label: "Готовность",
                  render: (pod) => (pod.ready ? "Готов" : "Не готов"),
                },
                {
                  key: "restarts",
                  label: "Перезапуски",
                  render: (pod) => pod.restart_count,
                },
                {
                  key: "node",
                  label: "Узел / IP",
                  render: (pod) => (
                    <>
                      {str(pod.node_name)}
                      <p className="muted">{pod.pod_ip}</p>
                    </>
                  ),
                },
                {
                  key: "version",
                  label: "Версия",
                  render: (pod) => str(pod.resource_version),
                },
              ]}
            />
            {related.pods.truncated && (
              <p className="section-body muted">
                Список Pods ограничен сервером.
              </p>
            )}
          </>
        )}
      </Panel>
      <Panel
        title="Связанные контроллеры"
        description="Для Deployment показаны ReplicaSets по селектору."
      >
        {!related.controllers.available ? (
          <Unavailable section={related.controllers} />
        ) : (
          <>
            <DataTable
              rows={related.controllers.items}
              rowKey={(controller) =>
                `${controller.kind}/${controller.namespace}/${controller.name}`
              }
              emptyTitle="Связанных контроллеров не найдено"
              columns={[
                {
                  key: "name",
                  label: "Контроллер",
                  render: (controller) => (
                    <>
                      <strong>{controller.name}</strong>
                      <p className="muted">
                        {controller.kind} · {controller.namespace}
                      </p>
                    </>
                  ),
                },
                {
                  key: "replicas",
                  label: "Готовых / всего",
                  render: (controller) =>
                    `${str(controller.ready_replicas)} / ${str(controller.replicas)}`,
                },
                {
                  key: "available",
                  label: "Доступных",
                  render: (controller) => str(controller.available_replicas),
                },
                {
                  key: "owner",
                  label: "Владелец",
                  render: (controller) =>
                    controller.owner_references
                      .map((owner) => `${owner.kind}/${owner.name}`)
                      .join(", ") || "Не указан",
                },
                {
                  key: "version",
                  label: "Версия",
                  render: (controller) => str(controller.resource_version),
                },
              ]}
            />
            {related.controllers.truncated && (
              <p className="section-body muted">
                Список контроллеров ограничен сервером.
              </p>
            )}
          </>
        )}
      </Panel>
      <Panel title="События описания">
        {!events.available ? (
          <Unavailable section={events} />
        ) : (
          <>
            <KubeEvents events={events.events} />
            {events.truncated && (
              <p className="section-body muted">
                Список событий ограничен сервером.
              </p>
            )}
          </>
        )}
      </Panel>
    </div>
  );
}
