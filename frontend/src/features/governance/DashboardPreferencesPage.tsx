import { useEffect, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Link, useBlocker } from "react-router-dom";
import { ArrowDown, ArrowUp, RotateCcw, Save } from "lucide-react";
import {
  dashboardLayoutApi,
  dashboardSectionLabels,
  defaultOverviewLayout,
  mergeOverviewLayout,
  type DashboardColumn,
  type DashboardSectionId,
  type OverviewLayout,
} from "@/api/dashboard-layout";
import { useSession } from "@/app/session";
import { useUnsavedProjectChange } from "@/app/unsaved-project-change";
import {
  Button,
  ConfirmDialog,
  EmptyState,
  ErrorState,
  Feedback,
  LoadingState,
  PageHeader,
  Panel,
} from "@/components/ui";
import { useDashboardLayout } from "./DashboardPreferences";

const sectionDescriptions: Record<DashboardSectionId, string> = {
  servers: "Состояние и нагрузка доступных серверов.",
  activity: "История ваших последних действий.",
  alerts: "Проблемы, которые требуют проверки.",
};

function LayoutEditor({
  query,
}: {
  query: ReturnType<typeof useDashboardLayout>;
}) {
  const client = useQueryClient();
  const [draft, setDraft] = useState<OverviewLayout | null>(null);
  const layout = draft ?? query.layout;
  const dirty = JSON.stringify(layout) !== JSON.stringify(query.layout);
  // A matching server response acknowledges this draft; future background
  // responses may then update the clean editor without discarding local edits.
  if (draft && !dirty) setDraft(null);
  const isDefault =
    JSON.stringify(layout) === JSON.stringify(defaultOverviewLayout());
  const mutation = useMutation({
    mutationFn: async (next: OverviewLayout) => {
      // Merge with the latest server value so unrelated preferences survive.
      const current = await dashboardLayoutApi.get(query.type);
      const raw = mergeOverviewLayout(current.layout, next);
      await dashboardLayoutApi.save(query.type, raw);
      return { raw };
    },
    onSuccess: ({ raw }) => {
      client.setQueryData(query.queryKey, { layout: raw });
      setDraft(null);
    },
  });
  const blocker = useBlocker(dirty || mutation.isPending);
  useUnsavedProjectChange(dirty, mutation.isPending);
  useEffect(() => {
    if (!dirty && !mutation.isPending) return;
    const warn = (event: BeforeUnloadEvent) => {
      event.preventDefault();
      event.returnValue = "";
    };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty, mutation.isPending]);
  useEffect(() => {
    if (blocker.state === "blocked" && !dirty && !mutation.isPending)
      blocker.proceed();
  }, [blocker, dirty, mutation.isPending]);
  const edit = (next: OverviewLayout) => {
    mutation.reset();
    setDraft(
      JSON.stringify(next) === JSON.stringify(query.layout) ? null : next,
    );
  };
  const move = (id: DashboardSectionId, column: DashboardColumn) => {
    edit({
      ...layout,
      columns: {
        main: layout.columns.main.filter((key) => key !== id),
        side: layout.columns.side.filter((key) => key !== id),
        [column]: [...layout.columns[column].filter((key) => key !== id), id],
      },
    });
  };
  const shift = (column: DashboardColumn, index: number, offset: number) => {
    const values = [...layout.columns[column]];
    [values[index], values[index + offset]] = [
      values[index + offset],
      values[index],
    ];
    edit({ ...layout, columns: { ...layout.columns, [column]: values } });
  };
  return (
    <>
      <Feedback
        error={mutation.error}
        success={
          mutation.isSuccess ? "Персональные настройки сохранены." : undefined
        }
      />
      <Panel
        title="Виджеты обзора"
        description="Измените расположение и видимость блоков. Сводка состояния остаётся в начале обзора."
      >
        <form
          onSubmit={(event) => {
            event.preventDefault();
            if (dirty && !mutation.isPending) mutation.mutate(layout);
          }}
        >
          <fieldset className="dashboard-editor" disabled={mutation.isPending}>
            {(["main", "side"] as const).map((column) => (
              <section
                key={column}
                aria-label={
                  column === "main" ? "Основная колонка" : "Боковая колонка"
                }
              >
                <h3>
                  {column === "main" ? "Основная колонка" : "Боковая колонка"}
                </h3>
                <p className="muted text-sm">
                  {column === "main"
                    ? "Широкие таблицы и история операций"
                    : "Короткие сводки и оповещения"}
                </p>
                <ol className="dashboard-editor-list">
                  {layout.columns[column].map((id, index) => (
                    <li
                      key={id}
                      className={
                        layout.hidden.includes(id)
                          ? "dashboard-card-hidden"
                          : ""
                      }
                    >
                      <label className="gov-check dashboard-card-title">
                        <input
                          type="checkbox"
                          aria-label={`Показывать: ${dashboardSectionLabels[id]}`}
                          checked={!layout.hidden.includes(id)}
                          onChange={(event) =>
                            edit({
                              ...layout,
                              hidden: event.target.checked
                                ? layout.hidden.filter((key) => key !== id)
                                : [...layout.hidden, id],
                            })
                          }
                        />
                        <span>
                          <strong>{dashboardSectionLabels[id]}</strong>
                          <small>{sectionDescriptions[id]}</small>
                        </span>
                      </label>
                      <div className="dashboard-card-controls">
                        <select
                          aria-label={`Колонка: ${dashboardSectionLabels[id]}`}
                          value={column}
                          onChange={(event) =>
                            move(id, event.target.value as DashboardColumn)
                          }
                        >
                          <option value="main">Основная колонка</option>
                          <option value="side">Боковая колонка</option>
                        </select>
                        <Button
                          size="icon"
                          aria-label={`Выше: ${dashboardSectionLabels[id]}`}
                          title="Переместить выше"
                          disabled={index === 0}
                          onClick={() => shift(column, index, -1)}
                        >
                          <ArrowUp size={15} />
                        </Button>
                        <Button
                          size="icon"
                          aria-label={`Ниже: ${dashboardSectionLabels[id]}`}
                          title="Переместить ниже"
                          disabled={index === layout.columns[column].length - 1}
                          onClick={() => shift(column, index, 1)}
                        >
                          <ArrowDown size={15} />
                        </Button>
                      </div>
                    </li>
                  ))}
                </ol>
                {layout.columns[column].length === 0 && (
                  <p className="muted text-sm">
                    Переместите сюда виджет из соседней колонки.
                  </p>
                )}
              </section>
            ))}
          </fieldset>
          {layout.hidden.length === 3 && (
            <p className="dashboard-editor-hint muted text-sm">
              Все виджеты скрыты. В обзоре останется только сводка состояния.
            </p>
          )}
          <div className="dashboard-editor-actions">
            <span className="muted text-sm" aria-live="polite">
              {dirty ? "Есть несохранённые изменения" : "Изменений нет"}
            </span>
            <div className="row dashboard-editor-buttons">
              {dirty && (
                <Button
                  disabled={mutation.isPending}
                  onClick={() => edit(query.layout)}
                >
                  Отменить изменения
                </Button>
              )}
              <Button
                disabled={mutation.isPending || isDefault}
                onClick={() => edit(defaultOverviewLayout())}
              >
                <RotateCcw size={15} />
                Исходное расположение
              </Button>
              <Button
                disabled={!dirty}
                loading={mutation.isPending}
                type="submit"
                variant="primary"
              >
                <Save size={15} />
                Сохранить расположение
              </Button>
            </div>
          </div>
        </form>
      </Panel>
      <ConfirmDialog
        open={blocker.state === "blocked"}
        onOpenChange={(open) => {
          if (!open && !mutation.isPending && blocker.state === "blocked")
            blocker.reset();
        }}
        title="Выйти без сохранения?"
        description={
          mutation.isPending
            ? "Сохранение уже началось. Дождитесь его завершения — затем страница откроется автоматически."
            : "Изменения расположения виджетов будут потеряны."
        }
        pending={mutation.isPending}
        confirmLabel="Выйти без сохранения"
        onConfirm={() => {
          if (blocker.state === "blocked") blocker.proceed();
        }}
      />
    </>
  );
}

export function DashboardPreferencesPage() {
  const { user } = useSession();
  const query = useDashboardLayout();
  return (
    <>
      <PageHeader
        eyebrow="Персональные настройки"
        title="Мой рабочий стол"
        description="Выберите, что показывать в обзоре. Расположение сохраняется для вашей учётной записи на всех устройствах и во всех проектах."
        actions={
          <Link className="btn btn-secondary" to="/">
            Открыть обзор
          </Link>
        }
      />
      {!user ? (
        <EmptyState title="Войдите в систему" />
      ) : query.isPending ? (
        <LoadingState />
      ) : query.error && !query.data ? (
        <ErrorState error={query.error} retry={() => void query.refetch()} />
      ) : (
        <>
          {query.error && (
            <ErrorState
              error={query.error}
              retry={() => void query.refetch()}
            />
          )}
          <LayoutEditor key={`${user.id}:${query.type}`} query={query} />
        </>
      )}
    </>
  );
}
