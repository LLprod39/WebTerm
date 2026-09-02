import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useMutation, useQuery } from "@tanstack/react-query";
import { Copy, GitBranch, Library, Plus, Sparkles, Wand2 } from "lucide-react";
import { api } from "@/api/client";
import {
  automationApi,
  studioBase,
  type Pipeline,
} from "@/api/automation";
import {
  Button,
  DataTable,
  Drawer,
  ErrorState,
  Feedback,
  Field,
  PageHeader,
  Panel,
  Skeleton,
  StatusBadge,
} from "@/components/ui";
import { formatDate } from "@/lib/utils";
import { formatNodeCount } from "./shared";
import { PipelineEditor } from "./editor/PipelineEditor";
import "./automation.css";

export function PipelineLibrary() {
  const query = useQuery({
    queryKey: ["automation", "pipelines"],
    queryFn: ({ signal }) => automationApi.pipelines(signal),
  });
  const [create, setCreate] = useState(false);
  const [templates, setTemplates] = useState(false);
  const [createMode, setCreateMode] = useState<"blank" | "template">("blank");
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const navigate = useNavigate();
  const mutation = useMutation({
    mutationFn: () => automationApi.createPipeline({ name, description }),
    onSuccess: (pipeline) => navigate(`/automation/pipelines/${pipeline.id}`),
  });

  const openCreate = () => {
    setCreateMode("blank");
    setName("");
    setDescription("");
    setCreate(true);
  };

  return (
    <>
      <PageHeader
        eyebrow="Автоматизация"
        title="Рабочие процессы"
        description="Соберите поток слева направо: триггер → шаги → результат."
        actions={
          <>
            <Button onClick={() => setTemplates(true)}>
              <Library size={15} />
              Шаблоны
            </Button>
            <Button variant="primary" onClick={openCreate}>
              <Plus size={15} />
              Новый процесс
            </Button>
          </>
        }
      />
      <Panel>
        {query.isPending ? (
          <Skeleton />
        ) : query.error ? (
          <ErrorState error={query.error} retry={() => void query.refetch()} />
        ) : (
          <DataTable
            rows={query.data ?? []}
            rowKey={(row) => row.id}
            searchValue={(row) =>
              `${row.name} ${row.description} ${row.tags.join(" ")}`
            }
            searchPlaceholder="Поиск процессов"
            emptyTitle="Создайте первый рабочий процесс"
            emptyDescription="Горизонтальный редактор: добавьте шаги, соедините их слева направо и сохраните."
            emptyAction={
              <Button variant="primary" onClick={openCreate}>
                Создать процесс
              </Button>
            }
            columns={[
              {
                key: "name",
                label: "Процесс",
                sortValue: (row) => row.name,
                render: (row) => (
                  <div className="table-name">
                    <span className="table-icon">
                      <GitBranch size={17} />
                    </span>
                    <div className="auto-row-title">
                      <Link to={`/automation/pipelines/${row.id}`}>
                        {row.name}
                      </Link>
                      <small>{row.description || "Без описания"}</small>
                    </div>
                  </div>
                ),
              },
              {
                key: "nodes",
                label: "Шаги",
                sortValue: (row) => row.node_count,
                render: (row) => formatNodeCount(row.node_count),
              },
              {
                key: "run",
                label: "Последний запуск",
                render: (row) =>
                  row.last_run ? (
                    <Link to={`/automation/runs/pipeline/${row.last_run.id}`}>
                      <StatusBadge status={row.last_run.status} />
                    </Link>
                  ) : (
                    <span className="auto-muted">Не запускался</span>
                  ),
              },
              {
                key: "updated",
                label: "Изменён",
                sortValue: (row) => row.updated_at,
                render: (row) => formatDate(row.updated_at),
              },
            ]}
          />
        )}
      </Panel>
      <Drawer
        open={create}
        onOpenChange={setCreate}
        title="Новый рабочий процесс"
      >
        <div className="auto-form">
          <div
            className="auto-create-choices"
            role="group"
            aria-label="Способ создания"
          >
            <button
              type="button"
              className={`auto-create-choice${createMode === "blank" ? " active" : ""}`}
              onClick={() => setCreateMode("blank")}
            >
              <span className="auto-create-choice-icon" aria-hidden>
                <Wand2 size={18} />
              </span>
              <span>
                <strong>С нуля</strong>
                <small>
                  Пустой холст с ручным триггером. Дальше добавляйте шаги вправо.
                </small>
              </span>
            </button>
            <button
              type="button"
              className={`auto-create-choice${createMode === "template" ? " active" : ""}`}
              onClick={() => setCreateMode("template")}
            >
              <span className="auto-create-choice-icon" aria-hidden>
                <Sparkles size={18} />
              </span>
              <span>
                <strong>Из шаблона</strong>
                <small>
                  Готовый поток с уже связанными шагами — быстрее старт.
                </small>
              </span>
            </button>
          </div>

          {createMode === "blank" ? (
            <form
              className="auto-form"
              onSubmit={(event) => {
                event.preventDefault();
                mutation.mutate();
              }}
            >
              <Field label="Название" htmlFor="pipeline-name">
                <input
                  id="pipeline-name"
                  required
                  value={name}
                  onChange={(event) => setName(event.target.value)}
                  placeholder="Например: Проверка диска → уведомление"
                />
              </Field>
              <Field label="Описание" htmlFor="pipeline-description">
                <textarea
                  id="pipeline-description"
                  value={description}
                  onChange={(event) => setDescription(event.target.value)}
                  placeholder="Кратко: что запускает процесс и какой результат"
                />
              </Field>
              <p className="muted text-sm">
                Поток читается слева направо. Триггер стартует выключенным —
                включите его после настройки шагов.
              </p>
              <Feedback error={mutation.error} />
              <Button
                type="submit"
                variant="primary"
                loading={mutation.isPending}
              >
                Создать процесс
              </Button>
            </form>
          ) : (
            <div className="auto-stack">
              <p className="muted text-sm">
                Выберите шаблон — процесс сразу откроется в редакторе.
              </p>
              <PipelineTemplates onUsed={() => setCreate(false)} compact />
              <Button
                variant="ghost"
                onClick={() => {
                  setCreate(false);
                  setTemplates(true);
                }}
              >
                <Library size={14} />
                Все шаблоны
              </Button>
            </div>
          )}
        </div>
      </Drawer>
      <Drawer
        open={templates}
        onOpenChange={setTemplates}
        title="Шаблоны рабочих процессов"
        wide
      >
        {templates && <PipelineTemplates />}
      </Drawer>
    </>
  );
}

function PipelineTemplates({
  onUsed,
  compact,
}: {
  onUsed?: () => void;
  compact?: boolean;
} = {}) {
  const query = useQuery({
    queryKey: ["automation", "pipeline-templates"],
    queryFn: ({ signal }) => automationApi.templates(signal),
  });
  const navigate = useNavigate();
  const useTemplate = useMutation({
    mutationFn: (slug: string) =>
      api.post<Pipeline>(`${studioBase}templates/${slug}/use/`),
    onSuccess: (pipeline) => {
      onUsed?.();
      navigate(`/automation/pipelines/${pipeline.id}`);
    },
  });
  return (
    <>
      <Feedback error={query.error || useTemplate.error} />
      {query.isPending ? (
        <Skeleton />
      ) : (
        <div className="auto-template-list">
          {(compact ? query.data?.slice(0, 4) : query.data)?.map((template) => (
            <article className="auto-template" key={template.slug}>
              <h3>{template.name}</h3>
              <p>{template.description}</p>
              <div className="auto-toolbar">
                <small className="muted">
                  {template.node_count != null
                    ? `${formatNodeCount(template.node_count)} · `
                    : ""}
                  {template.category}
                </small>
                <Button
                  size="sm"
                  loading={
                    useTemplate.isPending &&
                    useTemplate.variables === template.slug
                  }
                  onClick={() => useTemplate.mutate(template.slug)}
                >
                  <Copy size={13} />
                  Использовать
                </Button>
              </div>
            </article>
          ))}
        </div>
      )}
    </>
  );
}

export function PipelineWorkspace() {
  const { id } = useParams();
  const numericId = Number(id);
  const pipeline = useQuery({
    queryKey: ["automation", "pipeline", numericId],
    queryFn: ({ signal }) => automationApi.pipeline(numericId, signal),
    refetchOnWindowFocus: false,
  });
  const manifests = useQuery({
    queryKey: ["automation", "node-manifests"],
    queryFn: ({ signal }) => automationApi.manifests(signal),
    staleTime: 300000,
  });
  if (pipeline.isPending || manifests.isPending) return <Skeleton />;
  if (pipeline.error || manifests.error)
    return (
      <ErrorState
        error={pipeline.error || manifests.error}
        retry={() => {
          void pipeline.refetch();
          void manifests.refetch();
        }}
      />
    );
  return (
    <PipelineEditor
      key={numericId}
      pipeline={pipeline.data!}
      manifests={manifests.data!.nodes}
    />
  );
}
