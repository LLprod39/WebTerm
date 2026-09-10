import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { BookMarked, Plus, Save, ShieldCheck, Trash2 } from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { useUnsavedEdits, confirmDiscardEdits } from "./unsaved";
import { api } from "@/api/client";
import {
  automationApi,
  studioBase,
  type Skill,
  type SkillFile,
  type Values,
} from "@/api/automation";
import {
  Button,
  ConfirmDialog,
  DataTable,
  Drawer,
  ErrorState,
  Feedback,
  Field,
  PageHeader,
  Panel,
  Skeleton,
  StatusBadge,
  Tabs,
} from "@/components/ui";
import { KeyValues } from "./shared";

interface SkillValidation {
  results: { slug: string; errors: string[]; warnings: string[] }[];
  summary: {
    skills: number;
    errors: number;
    warnings: number;
    is_valid: boolean;
  };
}
export function SkillLibrary() {
  const query = useQuery({
    queryKey: ["automation", "skills"],
    queryFn: ({ signal }) => automationApi.skills(signal),
  });
  const [create, setCreate] = useState(false);
  const validate = useMutation({
    mutationFn: () =>
      api.post<SkillValidation>(`${studioBase}skills/validate/`, {
        strict: false,
      }),
  });
  return (
    <>
      <PageHeader
        eyebrow="Интеллект / Инструменты"
        title="Навыки"
        description="Инструкции, ограничения и рабочие материалы для агентов."
        actions={
          <>
            <Button
              loading={validate.isPending}
              onClick={() => validate.mutate()}
            >
              <ShieldCheck size={15} />
              Проверить каталог
            </Button>
            <Button variant="primary" onClick={() => setCreate(true)}>
              <Plus size={15} />
              Новый навык
            </Button>
          </>
        }
      />
      <Feedback error={validate.error} />
      {validate.data && <SkillValidationResult data={validate.data} />}
      <Panel>
        {query.isPending ? (
          <Skeleton />
        ) : query.error ? (
          <ErrorState error={query.error} retry={() => void query.refetch()} />
        ) : (
          <DataTable
            rows={query.data ?? []}
            rowKey={(r) => r.slug}
            searchValue={(r) =>
              `${r.name} ${r.description} ${r.service} ${r.tags.join(" ")}`
            }
            searchPlaceholder="Поиск навыков"
            emptyTitle="Доступных навыков пока нет"
            emptyDescription="Создайте набор инструкций или попросите владельца поделиться существующим навыком."
            emptyAction={
              <Button variant="primary" onClick={() => setCreate(true)}>
                Создать навык
              </Button>
            }
            columns={[
              {
                key: "name",
                label: "Навык",
                render: (r) => (
                  <div className="table-name">
                    <span className="table-icon">
                      <BookMarked size={17} />
                    </span>
                    <div className="auto-row-title">
                      <Link
                        to={`/intelligence/skills/${encodeURIComponent(r.slug)}`}
                      >
                        {r.name}
                      </Link>
                      <small>{r.description}</small>
                    </div>
                  </div>
                ),
              },
              {
                key: "category",
                label: "Назначение",
                render: (r) => (
                  <>
                    {r.category || "Общие операции"}
                    <small>{r.service}</small>
                  </>
                ),
              },
              {
                key: "risk",
                label: "Уровень контроля",
                render: (r) => (
                  <StatusBadge
                    status={
                      ["high", "critical"].includes(r.safety_level)
                        ? "warning"
                        : "info"
                    }
                  >
                    {r.safety_level || "standard"}
                  </StatusBadge>
                ),
              },
              {
                key: "owner",
                label: "Владелец",
                render: (r) => r.owner_username || "Системный",
              },
              {
                key: "access",
                label: "Доступ",
                render: (r) => (r.can_edit ? "Редактирование" : "Чтение"),
              },
            ]}
          />
        )}
      </Panel>
      <Drawer open={create} onOpenChange={setCreate} title="Создать навык" wide>
        {create && <SkillForm />}
      </Drawer>
    </>
  );
}
function SkillValidationResult({ data }: { data: SkillValidation }) {
  return (
    <div className="auto-validation">
      <StatusBadge status={data.summary.is_valid ? "success" : "warning"}>
        {data.summary.is_valid ? "Проверка пройдена" : "Обнаружены замечания"}
      </StatusBadge>
      <p>
        {data.summary.skills} навыков · {data.summary.errors} ошибок ·{" "}
        {data.summary.warnings} предупреждений
      </p>
      {data.results
        .filter((r) => r.errors.length || r.warnings.length)
        .map((r) => (
          <div key={r.slug}>
            <strong>{r.slug}</strong>
            {r.errors.map((msg, i) => (
              <p className="auto-danger-text" key={`e${i}`}>
                {msg}
              </p>
            ))}
            {r.warnings.map((msg, i) => (
              <p className="muted" key={`w${i}`}>
                {msg}
              </p>
            ))}
          </div>
        ))}
    </div>
  );
}
function SkillForm({ skill, done }: { skill?: Skill; done?: () => void }) {
  const navigate = useNavigate();
  const client = useQueryClient();
  const [name, setName] = useState(skill?.name ?? "");
  const [description, setDescription] = useState(skill?.description ?? "");
  const [slug, setSlug] = useState(skill?.slug ?? "");
  const [template, setTemplate] = useState("");
  const [service, setService] = useState(skill?.service ?? "");
  const [category, setCategory] = useState(skill?.category ?? "");
  const [safety, setSafety] = useState(skill?.safety_level || "standard");
  const [tags, setTags] = useState(skill?.tags.join(", ") ?? "");
  const [guards, setGuards] = useState(
    skill?.guardrail_summary?.join("\n") ?? "",
  );
  const [tools, setTools] = useState(
    skill?.recommended_tools?.join("\n") ?? "",
  );
  const [policy, setPolicy] = useState<Values>(skill?.runtime_policy ?? {});
  const [scripts, setScripts] = useState(false);
  const [references, setReferences] = useState(true);
  const templates = useQuery({
    queryKey: ["automation", "skill-templates"],
    queryFn: ({ signal }) =>
      api.get<
        { slug: string; name: string; description: string; defaults: Values }[]
      >(`${studioBase}skills/templates/`, signal),
    enabled: !skill,
  });
  const save = useMutation({
    mutationFn: async () => {
      const body = {
        name,
        description,
        slug: slug || undefined,
        template_slug: template || undefined,
        service,
        category,
        safety_level: safety,
        tags: tags
          .split(",")
          .map((s) => s.trim())
          .filter(Boolean),
        guardrail_summary: guards.split("\n").filter(Boolean),
        recommended_tools: tools.split("\n").filter(Boolean),
        runtime_policy: policy,
        with_scripts: scripts,
        with_references: references,
      };
      if (skill)
        return {
          skill: await api.put<Skill>(
            `${studioBase}skills/${encodeURIComponent(skill.slug)}/`,
            body,
          ),
        };
      return api.post<{ skill: Skill }>(`${studioBase}skills/scaffold/`, body);
    },
    onSuccess: (r) => {
      void client.invalidateQueries({ queryKey: ["automation", "skills"] });
      void client.invalidateQueries({
        queryKey: ["automation", "skill", r.skill.slug],
      });
      if (done) done();
      else navigate(`/intelligence/skills/${encodeURIComponent(r.skill.slug)}`);
    },
  });
  return (
    <form
      className="auto-form"
      onSubmit={(e) => {
        e.preventDefault();
        save.mutate();
      }}
    >
      {!skill && (
        <Field label="Шаблон" htmlFor="skill-template">
          <select
            id="skill-template"
            value={template}
            onChange={(e) => {
              setTemplate(e.target.value);
              const defaults = templates.data?.find(
                (t) => t.slug === e.target.value,
              )?.defaults;
              if (defaults) {
                setName(String(defaults.name ?? ""));
                setDescription(String(defaults.description ?? ""));
                setService(String(defaults.service ?? ""));
                setCategory(String(defaults.category ?? ""));
                setSafety(String(defaults.safety_level ?? "standard"));
                if (
                  defaults.runtime_policy &&
                  typeof defaults.runtime_policy === "object" &&
                  !Array.isArray(defaults.runtime_policy)
                )
                  setPolicy(defaults.runtime_policy);
                if (Array.isArray(defaults.guardrail_summary))
                  setGuards(defaults.guardrail_summary.join("\n"));
                if (Array.isArray(defaults.recommended_tools))
                  setTools(defaults.recommended_tools.join("\n"));
              }
            }}
          >
            <option value="">Создать с нуля</option>
            {templates.data?.map((t) => (
              <option key={t.slug} value={t.slug}>
                {t.name}
              </option>
            ))}
          </select>
        </Field>
      )}
      <div className="auto-form-grid">
        <Field label="Название" htmlFor="skill-name">
          <input
            id="skill-name"
            required
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
        </Field>
        <Field
          label="Идентификатор"
          htmlFor="skill-slug"
          description="Латинские буквы, цифры и дефисы."
        >
          <input
            id="skill-slug"
            disabled={!!skill}
            value={slug}
            pattern="[a-z0-9-]*"
            onChange={(e) => setSlug(e.target.value)}
          />
        </Field>
      </div>
      <Field label="Описание" htmlFor="skill-description">
        <textarea
          id="skill-description"
          required
          value={description}
          onChange={(e) => setDescription(e.target.value)}
        />
      </Field>
      <div className="auto-form-grid">
        <Field label="Сервис" htmlFor="skill-service">
          <input
            id="skill-service"
            value={service}
            onChange={(e) => setService(e.target.value)}
          />
        </Field>
        <Field label="Категория" htmlFor="skill-category">
          <input
            id="skill-category"
            value={category}
            onChange={(e) => setCategory(e.target.value)}
          />
        </Field>
        <Field label="Уровень контроля" htmlFor="skill-safety">
          <select
            id="skill-safety"
            value={safety}
            onChange={(e) => setSafety(e.target.value)}
          >
            {["low", "standard", "medium", "high", "critical"].map((level) => (
              <option key={level} value={level}>
                {level}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Теги через запятую" htmlFor="skill-tags">
          <input
            id="skill-tags"
            value={tags}
            onChange={(e) => setTags(e.target.value)}
          />
        </Field>
      </div>
      <Field label="Ограничения: одно на строку" htmlFor="skill-guards">
        <textarea
          id="skill-guards"
          value={guards}
          onChange={(e) => setGuards(e.target.value)}
        />
      </Field>
      <Field
        label="Рекомендуемые инструменты: по одному на строку"
        htmlFor="skill-tools"
      >
        <textarea
          id="skill-tools"
          value={tools}
          onChange={(e) => setTools(e.target.value)}
        />
      </Field>
      <KeyValues
        label="Политика исполнения"
        value={policy}
        onChange={setPolicy}
      />
      {!skill && (
        <>
          <label className="auto-check-row">
            <input
              type="checkbox"
              checked={scripts}
              onChange={(e) => setScripts(e.target.checked)}
            />
            Создать каталог скриптов
          </label>
          <label className="auto-check-row">
            <input
              type="checkbox"
              checked={references}
              onChange={(e) => setReferences(e.target.checked)}
            />
            Создать каталог материалов
          </label>
        </>
      )}
      <Feedback error={save.error} />
      <Button type="submit" variant="primary" loading={save.isPending}>
        <Save size={14} />
        {skill ? "Сохранить настройки" : "Создать навык"}
      </Button>
    </form>
  );
}
export function SkillWorkspace() {
  const { slug = "" } = useParams();
  const query = useQuery({
    queryKey: ["automation", "skill", slug],
    queryFn: ({ signal }) => automationApi.skill(slug, signal),
  });
  const [tab, setTab] = useState("instructions");
  const [settings, setSettings] = useState(false);
  const validate = useMutation({
    mutationFn: () =>
      api.post<SkillValidation>(`${studioBase}skills/validate/`, {
        slugs: [slug],
        strict: false,
      }),
  });
  if (query.isPending) return <Skeleton />;
  if (query.error)
    return (
      <ErrorState error={query.error} retry={() => void query.refetch()} />
    );
  const skill = query.data!;
  return (
    <>
      <PageHeader
        eyebrow="Интеллект / Навыки"
        title={skill.name}
        description={skill.description}
        actions={
          <>
            <Link className="btn btn-ghost" to="/intelligence/skills">
              К навыкам
            </Link>
            <Button
              loading={validate.isPending}
              onClick={() => validate.mutate()}
            >
              <ShieldCheck size={14} />
              Проверить
            </Button>
            {skill.can_edit && (
              <Button variant="primary" onClick={() => setSettings(true)}>
                Настройки
              </Button>
            )}
          </>
        }
      />
      <Feedback error={validate.error} />
      {validate.data && <SkillValidationResult data={validate.data} />}
      <Tabs
        value={tab}
        onChange={(value) => {
          if (confirmDiscardEdits()) setTab(value);
        }}
        items={[
          { value: "instructions", label: "Инструкции" },
          { value: "files", label: "Рабочие файлы" },
          ...(skill.can_share ? [{ value: "access", label: "Доступ" }] : []),
        ]}
      />
      {tab === "instructions" ? (
        <div className="auto-detail-grid">
          <Panel>
            <article className="auto-pad markdown">
              <ReactMarkdown remarkPlugins={[remarkGfm]}>
                {skill.content || "В навыке пока нет текста инструкций."}
              </ReactMarkdown>
            </article>
          </Panel>
          <Panel title="Правила применения">
            <div className="auto-summary">
              <StatusBadge
                status={
                  ["high", "critical"].includes(skill.safety_level)
                    ? "warning"
                    : "info"
                }
              >
                {skill.safety_level}
              </StatusBadge>
              <p className="muted text-sm">
                {skill.category} · {skill.service}
              </p>
              {skill.guardrail_summary?.map((g, i) => (
                <p key={i}>{g}</p>
              ))}
              <div className="auto-tags">
                {skill.recommended_tools?.map((t) => (
                  <span className="auto-tag" key={t}>
                    {t}
                  </span>
                ))}
              </div>
              <p className="muted text-sm">
                {skill.can_edit
                  ? "Вы можете редактировать этот навык."
                  : "Навык доступен для чтения."}
              </p>
            </div>
          </Panel>
        </div>
      ) : tab === "files" ? (
        <SkillFiles skill={skill} />
      ) : (
        <SkillSharing skill={skill} />
      )}
      <Drawer
        open={settings}
        onOpenChange={setSettings}
        title="Настройки навыка"
        wide
      >
        {settings && (
          <SkillForm skill={skill} done={() => setSettings(false)} />
        )}
      </Drawer>
    </>
  );
}
function SkillFiles({ skill }: { skill: Skill }) {
  const query = useQuery({
    queryKey: ["automation", "skill-workspace", skill.slug],
    queryFn: ({ signal }) => automationApi.skillWorkspace(skill.slug, signal),
    refetchOnWindowFocus: false,
  });
  const [path, setPath] = useState("SKILL.md");
  const [newOpen, setNewOpen] = useState(false);
  const [newPath, setNewPath] = useState("references/");
  const [remove, setRemove] = useState(false);
  const client = useQueryClient();
  const file = useQuery({
    queryKey: ["automation", "skill-file", skill.slug, path],
    queryFn: ({ signal }) =>
      api.get<SkillFile>(
        `${studioBase}skills/${encodeURIComponent(skill.slug)}/workspace/file/?path=${encodeURIComponent(path)}`,
        signal,
      ),
    refetchOnWindowFocus: false,
  });
  const refresh = () => {
    void client.invalidateQueries({
      queryKey: ["automation", "skill-workspace", skill.slug],
    });
    void client.invalidateQueries({
      queryKey: ["automation", "skill", skill.slug],
    });
    void client.invalidateQueries({
      queryKey: ["automation", "skill-file", skill.slug],
    });
  };
  const create = useMutation({
    mutationFn: () =>
      api.post(
        `${studioBase}skills/${encodeURIComponent(skill.slug)}/workspace/file/`,
        { path: newPath, content: "" },
      ),
    onSuccess: () => {
      refresh();
      setPath(newPath);
      setNewOpen(false);
    },
  });
  const deletion = useMutation({
    mutationFn: () =>
      api.delete(
        `${studioBase}skills/${encodeURIComponent(skill.slug)}/workspace/file/`,
        { path },
      ),
    onSuccess: () => {
      setPath("SKILL.md");
      setRemove(false);
      refresh();
    },
  });
  return (
    <>
      <Feedback error={create.error || deletion.error} />
      <Panel
        title="Файлы навыка"
        actions={
          skill.can_edit ? (
            <Button size="sm" onClick={() => setNewOpen(true)}>
              <Plus size={14} />
              Новый файл
            </Button>
          ) : undefined
        }
      >
        <div className="auto-files-grid">
          <aside className="auto-file-sidebar">
            {query.isPending ? (
              <Skeleton rows={3} />
            ) : query.error ? (
              <ErrorState error={query.error} />
            ) : (
              <div className="auto-file-list">
                {query.data?.files.map((f) => (
                  <button
                    key={f.path}
                    className={f.path === path ? "active" : ""}
                    onClick={() => {
                      if (confirmDiscardEdits()) setPath(f.path);
                    }}
                  >
                    {f.path}
                  </button>
                ))}
              </div>
            )}
          </aside>
          <div>
            {file.isPending ? (
              <Skeleton />
            ) : file.error ? (
              <ErrorState error={file.error} />
            ) : file.data ? (
              <SkillTextEditor
                key={`${skill.slug}:${path}:${file.data.content}`}
                skill={skill}
                file={file.data}
                done={refresh}
                remove={() => setRemove(true)}
              />
            ) : null}
          </div>
        </div>
      </Panel>
      <Drawer
        open={newOpen}
        onOpenChange={setNewOpen}
        title="Новый файл навыка"
      >
        <form
          className="auto-form"
          onSubmit={(e) => {
            e.preventDefault();
            create.mutate();
          }}
        >
          <Field
            label="Путь"
            htmlFor="skill-file-path"
            description="Разрешены каталоги references/, scripts/ и assets/."
          >
            <input
              id="skill-file-path"
              required
              value={newPath}
              onChange={(e) => setNewPath(e.target.value)}
            />
          </Field>
          <Feedback error={create.error} />
          <Button type="submit" variant="primary" loading={create.isPending}>
            Создать файл
          </Button>
        </form>
      </Drawer>
      <ConfirmDialog
        open={remove}
        onOpenChange={setRemove}
        title="Удалить файл?"
        description={`Файл ${path} будет удалён из навыка.`}
        onConfirm={() => deletion.mutate()}
        pending={deletion.isPending}
        confirmLabel="Удалить"
      />
    </>
  );
}
function SkillTextEditor({
  skill,
  file,
  done,
  remove,
}: {
  skill: Skill;
  file: SkillFile;
  done: () => void;
  remove: () => void;
}) {
  const [text, setText] = useState(file.content ?? "");
  const dirty = text !== (file.content ?? "");
  useUnsavedEdits(dirty);
  const save = useMutation({
    mutationFn: () =>
      api.put<{ validation: { errors: string[]; warnings: string[] } }>(
        `${studioBase}skills/${encodeURIComponent(skill.slug)}/workspace/file/`,
        { path: file.path, content: text },
      ),
    onSuccess: done,
  });
  return (
    <>
      <div className="auto-editor-header">
        <code>{file.path}</code>
        <StatusBadge status={dirty ? "draft" : "success"}>
          {dirty
            ? "Не сохранено"
            : file.editable
              ? "Сохранено"
              : "Только чтение"}
        </StatusBadge>
      </div>
      <textarea
        aria-label={`Редактор ${file.path}`}
        className="auto-editor"
        spellCheck={false}
        readOnly={!file.editable}
        value={text}
        onChange={(e) => setText(e.target.value)}
      />
      <div className="auto-pad">
        <Feedback error={save.error} />
        {save.data?.validation.errors.map((error, i) => (
          <p className="notice notice-danger" key={i}>
            {error}
          </p>
        ))}
      </div>
      {skill.can_edit && (
        <div className="auto-action-strip">
          <Button
            variant="primary"
            loading={save.isPending}
            disabled={!dirty}
            onClick={() => save.mutate()}
          >
            <Save size={14} />
            Сохранить файл
          </Button>
          {file.path !== "SKILL.md" && (
            <Button variant="ghost" onClick={remove}>
              <Trash2 size={14} />
              Удалить файл
            </Button>
          )}
        </div>
      )}
    </>
  );
}
function SkillSharing({ skill }: { skill: Skill }) {
  const [shared, setShared] = useState("unchanged");
  const [ids, setIds] = useState<number[]>(
    (skill as Skill & { shared_user_ids?: number[] }).shared_user_ids ?? [],
  );
  const users = useQuery({
    queryKey: ["automation", "studio-share-users"],
    queryFn: ({ signal }) =>
      api.get<{ id: number; username: string }[]>(
        `${studioBase}share-users/`,
        signal,
      ),
  });
  const mutation = useMutation({
    mutationFn: () =>
      api.put(`${studioBase}skills/${encodeURIComponent(skill.slug)}/`, {
        ...(shared !== "unchanged" ? { is_shared: shared === "enabled" } : {}),
        shared_user_ids: ids,
      }),
  });
  return (
    <Panel title="Доступ к навыку">
      <div className="auto-pad auto-form">
        <Field
          label="Общий доступ"
          htmlFor="skill-sharing-mode"
          description="Индивидуальные разрешения выберите ниже."
        >
          <select
            id="skill-sharing-mode"
            value={shared}
            onChange={(e) => setShared(e.target.value)}
          >
            <option value="unchanged">Не менять</option>
            <option value="enabled">Включить общий доступ</option>
            <option value="disabled">Отключить общий доступ</option>
          </select>
        </Field>
        {users.error ? (
          <ErrorState error={users.error} />
        ) : (
          users.data?.map((user) => (
            <label className="auto-check-row" key={user.id}>
              <input
                type="checkbox"
                checked={ids.includes(user.id)}
                onChange={(e) =>
                  setIds(
                    e.target.checked
                      ? [...ids, user.id]
                      : ids.filter((id) => id !== user.id),
                  )
                }
              />
              {user.username}
            </label>
          ))
        )}
        <Feedback
          error={mutation.error}
          success={mutation.isSuccess ? "Разрешения обновлены" : undefined}
        />
        <div>
          <Button
            variant="primary"
            loading={mutation.isPending}
            onClick={() => mutation.mutate()}
          >
            Сохранить разрешения
          </Button>
        </div>
      </div>
    </Panel>
  );
}
