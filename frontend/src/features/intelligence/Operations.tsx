import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link, useNavigate } from "react-router-dom";
import {
  intelligenceApi as service,
  type Agent,
  type Chat,
  type Details,
  type MemorySnapshot,
  type PlanTask,
} from "@/api/intelligence";
import {
  Button,
  ConfirmDialog,
  DataTable,
  Drawer,
  ErrorState,
  Field,
  JsonDetails,
  LoadingState,
  Panel,
} from "@/components/ui";
import { usePermission } from "@/app/session";
import { formatDate } from "@/lib/utils";
import { IntelStatus, record, text, useOperation } from "./common";

export function DutyDrawer({ onClose }: { onClose: () => void }) {
  const op = useOperation();
  const nav = useNavigate();
  const [confirm, setConfirm] = useState<"brief" | "enable" | "disable" | null>(
    null,
  );
  const q = useQuery({
    queryKey: ["intelligence", "duty"],
    queryFn: () => service.duty(),
  });
  return (
    <Drawer
      open
      onOpenChange={(v) => {
        if (!v && !op.pending) onClose();
      }}
      title="Дежурный оператор"
      description="Постоянный диалог для сводок и наблюдения за инфраструктурой."
    >
      {q.isPending ? (
        <LoadingState />
      ) : q.error ? (
        <ErrorState error={q.error} />
      ) : (
        q.data && (
          <div className="intel-form">
            <div className="intel-row">
              <strong>Автоматические сводки</strong>
              <IntelStatus
                value={q.data.duty_enabled ? "enabled" : "disabled"}
              />
            </div>
            <p className="muted">
              При включении серверный рабочий процесс готовит сводки по
              настроенным источникам. Доставка зависит от доступности этого
              процесса и модели.
            </p>
            <div className="intel-row">
              <Button
                onClick={() => {
                  nav(`/intelligence/chat/${q.data.id}`);
                  onClose();
                }}
              >
                Открыть диалог
              </Button>
              <Button
                onClick={() =>
                  setConfirm(q.data.duty_enabled ? "disable" : "enable")
                }
              >
                {q.data.duty_enabled
                  ? "Отключить дежурство"
                  : "Включить дежурство"}
              </Button>
              <Button variant="primary" onClick={() => setConfirm("brief")}>
                Подготовить сводку сейчас
              </Button>
            </div>
            {op.feedback}
          </div>
        )
      )}
      <ConfirmDialog
        open={!!confirm}
        onOpenChange={(v) => {
          if (!v) setConfirm(null);
        }}
        title={
          confirm === "brief"
            ? "Подготовить сводку?"
            : confirm === "enable"
              ? "Включить дежурство?"
              : "Отключить дежурство?"
        }
        description={
          confirm === "brief"
            ? "Оператор проверит доступный контекст и создаст сводку в дежурном диалоге. Будут использованы настроенные AI-ресурсы."
            : confirm === "enable"
              ? "Рабочий процесс начнёт автоматически создавать сводки для вашего аккаунта."
              : "Автоматическое создание сводок будет остановлено. История диалога сохранится."
        }
        confirmLabel="Подтвердить"
        pending={op.pending}
        onConfirm={() =>
          void op.run(
            () =>
              service.duty(
                confirm === "brief"
                  ? { brief_now: true }
                  : { enabled: confirm === "enable" },
              ),
            "Настройки дежурства обновлены",
            (data) => {
              setConfirm(null);
              if (confirm === "brief") {
                const chat = data.chat || data;
                nav(`/intelligence/chat/${chat.id}`);
                onClose();
              } else void q.refetch();
            },
          )
        }
      />
    </Drawer>
  );
}

export function RenameChatDrawer({
  chat,
  onClose,
}: {
  chat: Chat;
  onClose: () => void;
}) {
  const op = useOperation();
  const [title, setTitle] = useState(chat.title);
  return (
    <Drawer
      open
      onOpenChange={(v) => {
        if (!v && !op.pending) onClose();
      }}
      title="Название диалога"
      footer={
        <Button
          variant="primary"
          loading={op.pending}
          disabled={!title.trim()}
          onClick={() =>
            void op.run(
              () => service.patchChat(chat.id, { title: title.trim() }),
              "",
              onClose,
            )
          }
        >
          Сохранить
        </Button>
      }
    >
      <Field label="Название" htmlFor="chat-title">
        <input
          id="chat-title"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          maxLength={200}
        />
      </Field>
      {op.feedback}
    </Drawer>
  );
}

export function MemoryBulkDrawer({
  serverId,
  serverName,
  items,
  onClose,
}: {
  serverId: number;
  serverName: string;
  items: MemorySnapshot[];
  onClose: () => void;
}) {
  const op = useOperation();
  const [ids, setIds] = useState<number[]>([]);
  const [review, setReview] = useState(false);
  const chosen = items.filter((s) => ids.includes(s.id));
  return (
    <Drawer
      open
      onOpenChange={(v) => {
        if (!v && !op.pending) onClose();
      }}
      title="Удаление сведений"
      description={`Область: ${serverName}`}
      footer={
        <Button
          variant="danger"
          disabled={!chosen.length}
          onClick={() => setReview(true)}
        >
          Рассмотреть удаление · {chosen.length}
        </Button>
      }
    >
      <div className="intel-form">
        <p className="muted">
          Выберите сведения, которые больше не должны участвовать в ответах и
          обработке памяти.
        </p>
        <div className="intel-checkbox-list">
          {items.map((s) => (
            <label key={s.id}>
              <input
                type="checkbox"
                checked={ids.includes(s.id)}
                onChange={(e) =>
                  setIds(
                    e.target.checked
                      ? [...ids, s.id]
                      : ids.filter((id) => id !== s.id),
                  )
                }
              />
              <span>
                {s.title}
                <small>
                  {s.kind} · {formatDate(s.updated_at)}
                </small>
              </span>
            </label>
          ))}
        </div>
        {op.feedback}
      </div>
      <ConfirmDialog
        open={review}
        onOpenChange={setReview}
        title={`Удалить сведения: ${chosen.length}?`}
        description={
          <>
            <p>
              Удаление необратимо. Если активных сведений не останется, backend
              также очистит производную AI-память этого сервера.
            </p>
            <ul>
              {chosen.map((s) => (
                <li key={s.id}>{s.title}</li>
              ))}
            </ul>
          </>
        }
        typedText={serverName}
        confirmLabel="Удалить выбранные"
        pending={op.pending}
        onConfirm={() =>
          void op.run(
            () =>
              service.memoryAction(serverId, "snapshots/bulk-delete", {
                snapshot_ids: chosen.map((s) => s.id),
              }),
            "",
            () => {
              setReview(false);
              onClose();
            },
          )
        }
      />
    </Drawer>
  );
}

export function PlanTaskEditor({
  runId,
  task,
  onClose,
}: {
  runId: number;
  task: PlanTask;
  onClose: () => void;
}) {
  const op = useOperation();
  const [name, setName] = useState(task.name);
  const [description, setDescription] = useState(task.description);
  const [instruction, setInstruction] = useState("");
  return (
    <Drawer
      open
      onOpenChange={(v) => {
        if (!v && !op.pending) onClose();
      }}
      title="Задача плана"
      description="Изменение сохраняется в плане запуска."
      footer={
        <Button
          variant="primary"
          disabled={!name.trim()}
          loading={op.pending}
          onClick={() =>
            void op.run(
              () =>
                service.task(runId, task.id, {
                  action: "update",
                  name: name.trim(),
                  description,
                }),
              "",
              onClose,
            )
          }
        >
          Сохранить задачу
        </Button>
      }
    >
      <div className="intel-form">
        <Field label="Название задачи" htmlFor="plan-task-name">
          <input
            id="plan-task-name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            maxLength={200}
            disabled={op.pending}
          />
        </Field>
        <Field label="Описание" htmlFor="plan-task-description">
          <textarea
            id="plan-task-description"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            maxLength={1000}
            rows={6}
            disabled={op.pending}
          />
        </Field>
        <details>
          <summary>Уточнить с помощью AI</summary>
          <div className="intel-form">
            <p className="muted">
              AI переработает сохранённую задачу и сразу обновит план.
              Несохранённые поля выше в запрос не входят.
            </p>
            <Field label="Как изменить задачу" htmlFor="plan-task-instruction">
              <textarea
                id="plan-task-instruction"
                rows={3}
                value={instruction}
                onChange={(e) => setInstruction(e.target.value)}
                maxLength={4000}
                disabled={op.pending}
              />
            </Field>
            <Button
              disabled={!instruction.trim()}
              loading={op.pending}
              onClick={() =>
                void op.run(
                  () => service.refineTask(runId, task.id, instruction),
                  "Задача обновлена в плане",
                  (result) => {
                    setName(result.task.name);
                    setDescription(result.task.description);
                    setInstruction("");
                  },
                )
              }
            >
              Уточнить и сохранить в плане
            </Button>
          </div>
        </details>
        {op.feedback}
      </div>
    </Drawer>
  );
}

export const scheduleLabels: Record<string, string> = {
  manual: "Ручной запуск",
  interval: "Через интервал",
  daily: "Ежедневно",
  weekly: "По дням недели",
  monthly: "Ежемесячно",
  once: "Однократно",
};
export function ScheduleFields({
  value,
  onChange,
}: {
  value: Details;
  onChange: (value: Details) => void;
}) {
  const mode = text(value.mode, "manual");
  const change = (key: string, next: unknown) =>
    onChange({ ...value, [key]: next });
  const days = Array.isArray(value.weekdays) ? value.weekdays.map(Number) : [];
  return (
    <div className="intel-form">
      <Field
        label="Расписание"
        htmlFor="agent-schedule-mode"
        description="Расписание запускает реальные операции автоматически в пределах прав агента."
      >
        <select
          id="agent-schedule-mode"
          value={mode}
          onChange={(e) => change("mode", e.target.value)}
        >
          {Object.entries(scheduleLabels).map(([key, label]) => (
            <option key={key} value={key}>
              {label}
            </option>
          ))}
        </select>
      </Field>
      {mode === "interval" && (
        <Field label="Интервал, минут" htmlFor="agent-schedule-interval">
          <input
            id="agent-schedule-interval"
            type="number"
            min={1}
            max={10080}
            value={Number(value.interval_minutes) || 1}
            onChange={(e) => change("interval_minutes", Number(e.target.value))}
          />
        </Field>
      )}
      {mode !== "manual" && mode !== "interval" && (
        <>
          <Field label="Часовой пояс" htmlFor="agent-schedule-zone">
            <input
              id="agent-schedule-zone"
              value={text(value.timezone, "UTC")}
              placeholder="Asia/Qyzylorda"
              onChange={(e) => change("timezone", e.target.value)}
            />
          </Field>
          {mode === "once" ? (
            <Field
              label="Дата и время запуска в выбранном поясе"
              htmlFor="agent-schedule-once"
            >
              <input
                id="agent-schedule-once"
                type="datetime-local"
                value={text(value.run_at, "").slice(0, 16)}
                onChange={(e) => change("run_at", e.target.value)}
              />
            </Field>
          ) : (
            <Field label="Время запуска" htmlFor="agent-schedule-time">
              <input
                id="agent-schedule-time"
                type="time"
                value={text(value.time, "09:00")}
                onChange={(e) => change("time", e.target.value)}
              />
            </Field>
          )}
          {mode === "weekly" && (
            <Field label="Дни недели">
              <div className="intel-row">
                {["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"].map(
                  (day, index) => (
                    <label className="intel-check" key={day}>
                      <input
                        type="checkbox"
                        checked={days.includes(index)}
                        onChange={(e) =>
                          change(
                            "weekdays",
                            e.target.checked
                              ? [...days, index]
                              : days.filter((d) => d !== index),
                          )
                        }
                      />
                      {day}
                    </label>
                  ),
                )}
              </div>
            </Field>
          )}
          {mode === "monthly" && (
            <Field label="День месяца" htmlFor="agent-schedule-day">
              <input
                id="agent-schedule-day"
                type="number"
                min={1}
                max={31}
                value={Number(value.day_of_month) || 1}
                onChange={(e) => change("day_of_month", Number(e.target.value))}
              />
            </Field>
          )}
        </>
      )}
    </div>
  );
}

export function AgentRuntimeDrawer({ onClose }: { onClose: () => void }) {
  const canAutomate = usePermission("automation");
  const op = useOperation();
  const [confirm, setConfirm] = useState<{
    type: "dispatch" | "cleanup";
    agent?: Agent;
  } | null>(null);
  const q = useQuery({
    queryKey: ["intelligence", "schedules"],
    queryFn: service.schedules,
    enabled: canAutomate,
  });
  const [result, setResult] = useState<Details | null>(null);
  return (
    <Drawer
      open
      wide
      onOpenChange={(v) => {
        if (!v && !op.pending) onClose();
      }}
      title="Расписания и рабочие процессы"
      description="Состояние автоматических запусков и восстановление зависших записей."
    >
      <div className="intel-form">
        {canAutomate &&
          (q.isPending ? (
            <LoadingState />
          ) : q.error ? (
            <ErrorState error={q.error} />
          ) : (
            q.data && (
              <>
                <Panel title="Запуски по расписанию">
                  <DataTable
                    rows={q.data.scheduled_agents}
                    rowKey={(a) => a.id}
                    emptyTitle="Расписаний пока нет"
                    columns={[
                      {
                        key: "name",
                        label: "Агент",
                        render: (a) => (
                          <Link
                            className="text-link"
                            to={`/intelligence/agents/${a.id}`}
                          >
                            {a.name}
                          </Link>
                        ),
                      },
                      {
                        key: "schedule",
                        label: "Расписание",
                        render: (a) =>
                          scheduleLabels[text(a.schedule_config.mode)] ||
                          "По настройке",
                      },
                      {
                        key: "next",
                        label: "Следующий запуск",
                        render: (a) => formatDate(a.next_due_at),
                      },
                      {
                        key: "state",
                        label: "Состояние",
                        render: (a) => <IntelStatus value={a.schedule_state} />,
                      },
                      {
                        key: "action",
                        label: "Действия",
                        render: (a) => (
                          <Button
                            size="sm"
                            disabled={
                              !a.due_now || !!a.active_run_id || !a.is_enabled
                            }
                            onClick={() =>
                              setConfirm({ type: "dispatch", agent: a })
                            }
                          >
                            Запустить наступивший
                          </Button>
                        ),
                      },
                    ]}
                  />
                </Panel>
                <JsonDetails
                  data={q.data.worker_states}
                  label="Состояние рабочих процессов"
                />
                <JsonDetails
                  data={q.data.execution_readiness}
                  label="Готовность выполнения"
                />
              </>
            )
          ))}
        <Panel title="Восстановление состояния">
          <div className="intel-pad">
            <p className="muted">
              Backend проверит до 100 записей ваших запусков. Только
              подтверждённо зависшие выполнения будут помечены завершёнными с
              ошибкой; связанные задания очереди будут отменены.
            </p>
            <Button onClick={() => setConfirm({ type: "cleanup" })}>
              Проверить зависшие запуски
            </Button>
          </div>
        </Panel>
        {result && <JsonDetails data={result} label="Результат операции" />}
        {op.feedback}
      </div>
      <ConfirmDialog
        open={!!confirm}
        onOpenChange={(v) => {
          if (!v) setConfirm(null);
        }}
        title={
          confirm?.type === "dispatch"
            ? "Запустить наступившее расписание?"
            : "Обработать зависшие запуски?"
        }
        description={
          confirm?.type === "dispatch"
            ? `Агент «${confirm.agent?.name}» выполнит настроенную задачу. Backend повторно проверит время запуска и наличие активной работы.`
            : "Подтверждённо зависшие записи будут закрыты с ошибкой. Операция не откатывает ранее выполненные действия."
        }
        pending={op.pending}
        confirmLabel="Продолжить"
        onConfirm={() =>
          void op.run(
            () =>
              confirm?.type === "dispatch"
                ? service.dispatchSchedules([confirm.agent!.id])
                : service.cleanupRuns(),
            "Операция завершена",
            (data) => {
              setResult(record(data));
              setConfirm(null);
            },
          )
        }
      />
    </Drawer>
  );
}
