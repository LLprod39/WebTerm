import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, RefreshCw, Sparkles } from "lucide-react";
import { api, ApiError } from "@/api/client";
import {
  automationApi,
  playbookBase,
  type Playbook,
  type Validation,
  type Values,
} from "@/api/automation";
import { usePermission } from "@/app/session";
import {
  Button,
  ConfirmDialog,
  DataTable,
  Feedback,
  Field,
  Panel,
  Skeleton,
  StatusBadge,
} from "@/components/ui";
import { formatDate } from "@/lib/utils";
import { KeyValues, TargetPicker, ValidationResult } from "./shared";
import {
  compatibilityExpectation,
  type CompatibilityBase,
} from "./compatibility";

interface Proposal {
  adapted_yaml: string;
  changes: string[];
  assumptions: string[];
  report: Validation;
  semantic_guard: { passed: boolean; violations?: string[] };
}
interface Adaptation {
  base: CompatibilityBase;
  proposal: Proposal;
}
export function PlaybookCompatibility({ playbook }: { playbook: Playbook }) {
  const hasServers = usePermission("servers");
  const servers = useQuery({
    queryKey: ["automation", "servers"],
    queryFn: ({ signal }) => automationApi.servers(signal),
    enabled: hasServers,
  });
  const [serverIds, setServerIds] = useState<number[]>([]);
  const [bindings, setBindings] = useState<Values>({});
  const [path, setPath] = useState("");
  const [instruction, setInstruction] = useState("");
  const [proposal, setProposal] = useState<Adaptation | null>(null);
  const [confirm, setConfirm] = useState(false);
  const [success, setSuccess] = useState("");
  const client = useQueryClient();
  const history = useQuery({
    queryKey: ["automation", "compatibility-history", playbook.id],
    queryFn: ({ signal }) =>
      api.get<{
        revisions: {
          id: number;
          status: string;
          change_summary: string[];
          created_at: string;
          active: boolean;
        }[];
      }>(`${playbookBase}${playbook.id}/compatibility/revisions/`, signal),
  });
  const analyze = useMutation({
    mutationFn: () =>
      api.post<{ report: Validation; base: CompatibilityBase }>(
        `${playbookBase}${playbook.id}/compatibility/analyze/`,
        {
          path,
          server_ids: serverIds,
          inventory_bindings: bindings,
          syntax_check: true,
        },
      ),
  });
  const adapt = useMutation({
    mutationFn: () =>
      api.post<Adaptation>(
        `${playbookBase}${playbook.id}/compatibility/adapt/`,
        { path, instruction, inventory_bindings: bindings },
      ),
    onSuccess: (data) => {
      setProposal(data);
      setSuccess("");
    },
  });
  const source = useQuery({
    queryKey: [
      "automation",
      "compatibility-source",
      playbook.id,
      proposal?.base,
    ],
    queryFn: ({ signal }) =>
      api.get<{ file: { content: string; sha256: string } }>(
        `${playbookBase}${playbook.id}/draft/file/?view=current&path=${encodeURIComponent(proposal!.base.path)}`,
        signal,
      ),
    enabled: !!proposal,
    refetchOnWindowFocus: false,
  });
  const apply = useMutation({
    mutationFn: () =>
      api.post(`${playbookBase}${playbook.id}/compatibility/apply/`, {
        ...compatibilityExpectation(proposal!.base),
        adapted_yaml: proposal!.proposal.adapted_yaml,
        inventory_bindings: bindings,
        change_summary: proposal!.proposal.changes,
      }),
    onSuccess: () => {
      setConfirm(false);
      setProposal(null);
      setSuccess(
        "Адаптация применена к черновику. Создайте и проверьте версию перед публикацией.",
      );
      void client.invalidateQueries({
        queryKey: ["automation", "playbook-draft", playbook.id],
      });
      void client.invalidateQueries({
        queryKey: ["automation", "playbook-files", playbook.id],
      });
      void client.invalidateQueries({
        queryKey: ["automation", "playbook", playbook.id],
      });
      void history.refetch();
    },
  });
  const clear = () => {
    setProposal(null);
    analyze.reset();
    setSuccess("");
  };
  return (
    <div className="auto-stack">
      <Panel
        title="Проверка совместимости"
        description="Анализ сохранённого YAML и адресная адаптация под окружение."
      >
        <div className="auto-pad auto-form">
          <Field
            label="Файл проекта"
            htmlFor="compat-path"
            description="Оставьте пустым для основного playbook. Для проекта можно указать относительный путь YAML."
          >
            <input
              id="compat-path"
              value={path}
              onChange={(e) => {
                setPath(e.target.value);
                clear();
              }}
            />
          </Field>
          {hasServers && (
            <TargetPicker
              servers={servers.data?.servers ?? []}
              value={serverIds}
              onChange={(value) => {
                setServerIds(value);
                clear();
              }}
            />
          )}
          <KeyValues
            label="Сопоставления inventory"
            value={bindings}
            onChange={(value) => {
              setBindings(value);
              clear();
            }}
          />
          <Button loading={analyze.isPending} onClick={() => analyze.mutate()}>
            <Check size={14} />
            Проверить совместимость
          </Button>
          {analyze.data && <ValidationResult value={analyze.data.report} />}
          <Feedback
            error={analyze.error || adapt.error || apply.error}
            success={success}
          />
          {playbook.capabilities.can_edit && (
            <>
              <Field
                label="Что нужно адаптировать"
                htmlFor="compat-instruction"
              >
                <textarea
                  id="compat-instruction"
                  rows={3}
                  value={instruction}
                  onChange={(e) => {
                    setInstruction(e.target.value);
                    setProposal(null);
                  }}
                  placeholder="Опишите требования целевого окружения"
                />
              </Field>
              <Button
                loading={adapt.isPending}
                disabled={!instruction.trim()}
                onClick={() => adapt.mutate()}
              >
                <Sparkles size={14} />
                Подготовить адаптацию
              </Button>
            </>
          )}
        </div>
      </Panel>
      {proposal && (
        <Panel
          title="Предложенные изменения"
          description={`Файл ${proposal.base.path} · черновик v${proposal.base.draft_version}`}
        >
          <div className="auto-pad">
            <StatusBadge
              status={
                proposal.proposal.semantic_guard.passed ? "success" : "error"
              }
            >
              {proposal.proposal.semantic_guard.passed
                ? "Проверка сохранения поведения пройдена"
                : "Проверка сохранения поведения не пройдена"}
            </StatusBadge>
            <ul className="auto-change-list">
              {proposal.proposal.changes.map((change, i) => (
                <li key={i}>{change}</li>
              ))}
            </ul>
            {proposal.proposal.assumptions.map((item, i) => (
              <p className="notice notice-warning" key={i}>
                {item}
              </p>
            ))}
            <ValidationResult value={proposal.proposal.report} />
          </div>
          <div className="auto-compat-diff">
            <div>
              <h3>Исходный файл</h3>
              {source.isPending ? (
                <Skeleton />
              ) : source.data?.file.sha256 === proposal.base.content_hash ? (
                <pre className="auto-source">{source.data.file.content}</pre>
              ) : (
                <p className="auto-pad notice notice-warning">
                  Исходная версия изменилась. Подготовьте адаптацию снова.
                </p>
              )}
            </div>
            <div>
              <h3>После адаптации</h3>
              <pre className="auto-source">
                {proposal.proposal.adapted_yaml ||
                  "Применение заблокировано проверкой поведения."}
              </pre>
            </div>
          </div>
          <div className="auto-action-strip">
            <Button
              variant="primary"
              disabled={
                !proposal.proposal.adapted_yaml ||
                !proposal.proposal.semantic_guard.passed ||
                source.data?.file.sha256 !== proposal.base.content_hash
              }
              onClick={() => setConfirm(true)}
            >
              Применить к черновику
            </Button>
            <Button onClick={() => setProposal(null)}>Отклонить</Button>
          </div>
          {apply.error instanceof ApiError && apply.error.status === 409 && (
            <p className="auto-pad notice notice-warning">
              Черновик изменился после анализа. Повторите подготовку адаптации.
            </p>
          )}
        </Panel>
      )}
      <Panel title="История адаптаций">
        {history.isPending ? (
          <Skeleton />
        ) : (
          <DataTable
            rows={history.data?.revisions ?? []}
            rowKey={(r) => r.id}
            emptyTitle="Адаптаций пока нет"
            columns={[
              {
                key: "status",
                label: "Статус",
                render: (r) => <StatusBadge status={r.status} />,
              },
              {
                key: "changes",
                label: "Изменения",
                render: (r) =>
                  Array.isArray(r.change_summary)
                    ? r.change_summary.join("; ")
                    : r.change_summary,
              },
              {
                key: "created",
                label: "Создана",
                render: (r) => formatDate(r.created_at),
              },
            ]}
          />
        )}
        <Feedback error={history.error} />
      </Panel>
      <ConfirmDialog
        open={confirm}
        onOpenChange={setConfirm}
        title="Применить адаптацию?"
        description="Проверенный вариант обновит сохранённый черновик. Сервер повторно проверит версию, состав проекта и сохранение поведения."
        confirmLabel="Применить"
        onConfirm={() => apply.mutate()}
        pending={apply.isPending}
      />
    </div>
  );
}

interface RefreshPreview {
  preview: {
    content_hash: string;
    selected_entrypoint: string;
    file_count: number;
  };
  source: Record<string, string>;
  refresh: {
    base_revision_id: number;
    entrypoint: string;
    diff: {
      added: string[];
      removed: string[];
      changed: string[];
      unchanged_count: number;
    };
  };
}
export function GitlabRefresh({ playbook }: { playbook: Playbook }) {
  const [token, setToken] = useState("");
  const [entrypoint, setEntrypoint] = useState("");
  const [preview, setPreview] = useState<RefreshPreview | null>(null);
  const [confirm, setConfirm] = useState(false);
  const [success, setSuccess] = useState("");
  const client = useQueryClient();
  const inspect = useMutation({
    mutationFn: () =>
      api.post<RefreshPreview>(
        `${playbookBase}${playbook.id}/gitlab/refresh/preview/`,
        { token, entrypoint },
      ),
    onSuccess: (data) => {
      setPreview(data);
      setSuccess("");
    },
  });
  const commit = useMutation({
    mutationFn: () =>
      api.post<{ revision: { number: number } }>(
        `${playbookBase}${playbook.id}/gitlab/refresh/commit/`,
        {
          token,
          entrypoint: preview!.refresh.entrypoint,
          expected_entrypoint: preview!.refresh.entrypoint,
          expected_base_revision_id: preview!.refresh.base_revision_id,
          expected_content_hash: preview!.preview.content_hash,
        },
      ),
    onSuccess: (data) => {
      setConfirm(false);
      setPreview(null);
      setToken("");
      setSuccess(
        `Версия ${data.revision.number} импортирована. Откройте её на вкладке «Версии» для проверки и публикации.`,
      );
      void client.invalidateQueries({
        queryKey: ["automation", "revisions", playbook.id],
      });
    },
  });
  const rows = preview
    ? [
        ...preview.refresh.diff.added.map((path) => ({
          path,
          status: "Добавлен",
        })),
        ...preview.refresh.diff.changed.map((path) => ({
          path,
          status: "Изменён",
        })),
        ...preview.refresh.diff.removed.map((path) => ({
          path,
          status: "Удалён",
        })),
      ]
    : [];
  return (
    <Panel
      title="Обновление из GitLab"
      description="Сравните проект с последней импортированной версией и сохраните новую версию для проверки."
    >
      <div className="auto-pad auto-form">
        <p className="mono">
          {`${playbook.source?.host}/${playbook.source?.project}`} ·{" "}
          {playbook.source?.ref}
        </p>
        <Field
          label="Основной YAML файл"
          htmlFor="refresh-entrypoint"
          description="Пустое значение сохраняет текущий путь."
        >
          <input
            id="refresh-entrypoint"
            value={entrypoint}
            onChange={(e) => {
              setEntrypoint(e.target.value);
              setPreview(null);
            }}
          />
        </Field>
        <Field label="Токен GitLab (если нужен)" htmlFor="refresh-token">
          <input
            id="refresh-token"
            type="password"
            autoComplete="off"
            value={token}
            onChange={(e) => {
              setToken(e.target.value);
              setPreview(null);
            }}
          />
        </Field>
        <Feedback error={inspect.error || commit.error} success={success} />
        <Button loading={inspect.isPending} onClick={() => inspect.mutate()}>
          <RefreshCw size={14} />
          Сравнить с GitLab
        </Button>
        {preview && (
          <>
            <p>
              {preview.preview.file_count} файлов ·{" "}
              {preview.refresh.diff.unchanged_count} без изменений
            </p>
            <DataTable
              rows={rows}
              rowKey={(r) => r.path}
              emptyTitle="Изменений в файлах нет"
              columns={[
                {
                  key: "path",
                  label: "Файл",
                  render: (r) => <code>{r.path}</code>,
                },
                { key: "status", label: "Изменение", render: (r) => r.status },
              ]}
            />
            <Button variant="primary" onClick={() => setConfirm(true)}>
              Импортировать новую версию
            </Button>
          </>
        )}
        <ConfirmDialog
          open={confirm}
          onOpenChange={setConfirm}
          title="Импортировать обновление?"
          description="Будет создана отдельная версия плейбука. Публикация выполняется после проверки на вкладке «Версии»."
          confirmLabel="Импортировать"
          onConfirm={() => commit.mutate()}
          pending={commit.isPending}
        />
      </div>
    </Panel>
  );
}
