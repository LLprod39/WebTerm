import { useState, type FormEvent } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus, Trash2 } from "lucide-react";
import {
  serverGroupsApi,
  type GroupContext as Context,
} from "@/api/server-groups";
import {
  Button,
  ConfirmDialog,
  ErrorState,
  Feedback,
  Field,
  LoadingState,
} from "@/components/ui";
import { useUnsavedEditsBlocker } from "@/features/automation/unsaved";

export function GroupContext({
  groupId,
  canEdit,
}: {
  groupId: number;
  canEdit: boolean;
}) {
  const query = useQuery({
    queryKey: ["group-context", groupId],
    queryFn: ({ signal }) => serverGroupsApi.context(groupId, signal),
  });
  if (query.isPending) return <LoadingState />;
  if (query.error)
    return (
      <ErrorState error={query.error} retry={() => void query.refetch()} />
    );
  return (
    <ContextEditor key={groupId} initial={query.data!} canEdit={canEdit} />
  );
}
function ContextEditor({
  initial,
  canEdit,
}: {
  initial: Context;
  canEdit: boolean;
}) {
  const client = useQueryClient();
  const [rules, setRules] = useState(initial.rules);
  const [forbidden, setForbidden] = useState(
    initial.forbidden_commands.join("\n"),
  );
  const [variables, setVariables] = useState(
    Object.entries(initial.environment_vars).map(([key, value]) => ({
      id: crypto.randomUUID(),
      key,
      value: String(value),
    })),
  );
  const [visible, setVisible] = useState(false);
  const payload = {
    rules,
    forbidden_commands: forbidden
      .split("\n")
      .map((item) => item.trim())
      .filter(Boolean),
    environment_vars: Object.fromEntries(
      variables.map((item) => [item.key.trim(), item.value]),
    ),
  };
  const [saved, setSaved] = useState(JSON.stringify(payload));
  const dirty = canEdit && JSON.stringify(payload) !== saved;
  const blocker = useUnsavedEditsBlocker(dirty);
  const invalidVariables = variables.some(
    (item) =>
      !item.key.trim() ||
      variables.filter((other) => other.key.trim() === item.key.trim()).length >
        1,
  );
  const save = useMutation({
    mutationKey: ["server-group", initial.id],
    mutationFn: () => serverGroupsApi.saveContext(initial.id, payload),
    onSuccess: () => {
      setSaved(JSON.stringify(payload));
      void client.invalidateQueries({
        queryKey: ["group-context", initial.id],
      });
    },
  });
  function submit(event: FormEvent) {
    event.preventDefault();
    if (canEdit && dirty && !invalidVariables && !save.isPending) save.mutate();
  }
  return (
    <>
      <form onSubmit={submit}>
        <fieldset
          className="stack"
          disabled={save.isPending}
          style={{ border: 0, padding: 0, margin: 0, minWidth: 0 }}
        >
          <Field
            label="Правила работы с группой"
            htmlFor="group-rules"
            description="Общие ограничения и рабочие инструкции для AI."
          >
            <textarea
              id="group-rules"
              rows={8}
              value={rules}
              disabled={!canEdit}
              onChange={(event) => setRules(event.target.value)}
            />
          </Field>
          <Field
            label="Запрещённые команды"
            htmlFor="group-forbidden"
            description="По одной команде или шаблону на строку."
          >
            <textarea
              id="group-forbidden"
              rows={5}
              value={forbidden}
              disabled={!canEdit}
              className="mono"
              onChange={(event) => setForbidden(event.target.value)}
            />
          </Field>
          {canEdit && (
            <details>
              <summary>
                Переменные окружения
                {variables.length ? ` · ${variables.length}` : ""}
              </summary>
              <div className="stack section-body">
                <div className="row spread">
                  <p className="muted text-sm">
                    Общие значения для серверов группы.
                  </p>
                  {!!variables.length && (
                    <Button size="sm" onClick={() => setVisible(!visible)}>
                      {visible ? "Скрыть значения" : "Показать значения"}
                    </Button>
                  )}
                </div>
                {variables.map((item) => (
                  <div className="row" key={item.id}>
                    <input
                      aria-label="Имя переменной"
                      placeholder="VARIABLE_NAME"
                      value={item.key}
                      onChange={(event) =>
                        setVariables(
                          variables.map((other) =>
                            other.id === item.id
                              ? { ...other, key: event.target.value }
                              : other,
                          ),
                        )
                      }
                    />
                    <input
                      aria-label={`Значение ${item.key || "переменной"}`}
                      type={visible ? "text" : "password"}
                      autoComplete="off"
                      value={item.value}
                      onChange={(event) =>
                        setVariables(
                          variables.map((other) =>
                            other.id === item.id
                              ? { ...other, value: event.target.value }
                              : other,
                          ),
                        )
                      }
                    />
                    <Button
                      size="icon"
                      aria-label={`Удалить переменную ${item.key}`}
                      onClick={() =>
                        setVariables(
                          variables.filter((other) => other.id !== item.id),
                        )
                      }
                    >
                      <Trash2 size={14} />
                    </Button>
                  </div>
                ))}
                {invalidVariables && (
                  <p className="field-error" role="alert">
                    У каждой переменной должно быть уникальное непустое имя.
                  </p>
                )}
                <Button
                  size="sm"
                  onClick={() =>
                    setVariables([
                      ...variables,
                      { id: crypto.randomUUID(), key: "", value: "" },
                    ])
                  }
                >
                  <Plus size={14} />
                  Добавить переменную
                </Button>
              </div>
            </details>
          )}
          <Feedback
            error={save.error}
            success={
              save.isSuccess && !dirty ? "Правила группы сохранены." : undefined
            }
          />
          {canEdit && (
            <Button
              type="submit"
              variant="primary"
              disabled={!dirty || invalidVariables}
              loading={save.isPending}
            >
              Сохранить правила
            </Button>
          )}
        </fieldset>
      </form>
      <ConfirmDialog
        open={blocker.state === "blocked"}
        onOpenChange={(open) => {
          if (!open && blocker.state === "blocked" && !save.isPending)
            blocker.reset();
        }}
        title="Закрыть без сохранения?"
        description="Изменения правил и переменных группы будут потеряны."
        confirmLabel="Не сохранять"
        pending={save.isPending}
        onConfirm={() => {
          if (blocker.state === "blocked" && !save.isPending) blocker.proceed();
        }}
      />
    </>
  );
}
