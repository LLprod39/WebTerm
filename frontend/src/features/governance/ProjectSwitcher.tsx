import { useId, useState, type ReactNode } from "react";
import {
  useIsMutating,
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import {
  ArrowLeft,
  Building2,
  ChevronDown,
  Plus,
  Search,
  Trash2,
  X,
} from "lucide-react";
import { api, ApiError } from "@/api/client";
import {
  governanceApi,
  type Project,
  type ProjectMember,
} from "@/api/governance";
import {
  Button,
  ConfirmDialog,
  DataTable,
  Drawer,
  EmptyState,
  ErrorState,
  Feedback,
  LoadingState,
  StatusBadge,
} from "@/components/ui";
import { useSession } from "@/app/session";
import {
  hasPendingProjectChanges,
  hasUnsavedProjectChanges,
} from "@/app/unsaved-project-change";
import { FormField, dateTime } from "./shared";

const roles: Record<string, string> = {
  owner: "Владелец",
  admin: "Администратор",
  operator: "Оператор",
  viewer: "Наблюдатель",
};
const roleHelp: Record<string, string> = {
  admin: "Управляет участниками и может создавать ресурсы в проекте.",
  operator: "Может создавать ресурсы в проекте, без управления участниками.",
  viewer: "Не управляет участниками и не создаёт ресурсы в проекте.",
};
const editableRoles = Object.entries(roles).filter(
  ([value]) => value !== "owner",
);
const duplicateMessage =
  "Этот пользователь уже участвует в проекте. Измените его роль в списке участников.";

function existingMember(members: ProjectMember[], identity: string) {
  const normalized = identity.trim().toLocaleLowerCase();
  return (
    !!normalized &&
    members.some(
      (member) =>
        member.username.toLocaleLowerCase() === normalized ||
        member.email.toLocaleLowerCase() === normalized,
    )
  );
}

function ProjectMembers({ project }: { project: Project }) {
  const { user } = useSession();
  const client = useQueryClient();
  const roleHelpId = useId();
  const [identity, setIdentity] = useState("");
  const [role, setRole] = useState("viewer");
  const [feedback, setFeedback] = useState<{
    error?: unknown;
    success?: string;
  }>({});
  const [deleting, setDeleting] = useState<ProjectMember | null>(null);
  const [changingRole, setChangingRole] = useState<{
    member: ProjectMember;
    role: string;
  } | null>(null);
  const queryOptions = {
    queryKey: ["governance", "project-members", project.id],
    queryFn: ({ signal }: { signal: AbortSignal }) =>
      api.get<{ members: ProjectMember[] }>(
        `/api/projects/${project.id}/members/`,
        signal,
      ),
  };
  const query = useQuery(queryOptions);
  const mutationKey = ["governance", "project-member-mutation", project.id];
  const refresh = async () => {
    await Promise.all([
      client.invalidateQueries({ queryKey: queryOptions.queryKey }),
      client.invalidateQueries({ queryKey: ["governance", "projects"] }),
      client.invalidateQueries({ queryKey: ["session"] }),
    ]);
  };
  const onMutate = () => setFeedback({});
  const onError = (error: unknown) => setFeedback({ error });
  const add = useMutation({
    mutationKey,
    mutationFn: async (input: { username: string; role: string }) => {
      // The backend POST is an upsert. Check a fresh full member list before it
      // so adding an existing person does not silently overwrite their role.
      const current = await client.fetchQuery({
        ...queryOptions,
        staleTime: 0,
      });
      if (existingMember(current.members, input.username))
        throw new Error(duplicateMessage);
      return api.post(`/api/projects/${project.id}/members/`, input);
    },
    onMutate,
    onError: (error: unknown) =>
      onError(
        error instanceof ApiError &&
          error.status === 404 &&
          /user not found/i.test(error.message)
          ? new Error(
              "Пользователь не найден. Укажите логин или рабочую почту существующего пользователя.",
            )
          : error,
      ),
    onSuccess: async () => {
      await refresh();
      setIdentity("");
      setFeedback({ success: "Участник добавлен." });
    },
  });
  const update = useMutation({
    mutationKey,
    mutationFn: ({
      user_id,
      role: nextRole,
    }: {
      user_id: number;
      role: string;
    }) =>
      api.patch(`/api/projects/${project.id}/members/${user_id}/`, {
        role: nextRole,
      }),
    onMutate,
    onError,
    onSuccess: async () => {
      await refresh();
      setChangingRole(null);
      setFeedback({ success: "Роль участника изменена." });
    },
  });
  const remove = useMutation({
    mutationKey,
    mutationFn: (id: number) =>
      api.delete(`/api/projects/${project.id}/members/${id}/`),
    onMutate,
    onError,
    onSuccess: async () => {
      await refresh();
      setDeleting(null);
      setFeedback({ success: "Участник убран из проекта." });
    },
  });
  const pending = add.isPending || update.isPending || remove.isPending;
  const duplicate = existingMember(query.data?.members ?? [], identity);
  return (
    <div className="gov-project-members" aria-busy={pending}>
      <Feedback {...feedback} />
      {project.can_manage && (
        <form
          className="gov-form gov-project-member-form"
          onSubmit={(event) => {
            event.preventDefault();
            if (pending || !query.isSuccess || !identity.trim() || duplicate)
              return;
            add.mutate({ username: identity.trim(), role });
          }}
        >
          <fieldset disabled={pending || !query.isSuccess}>
            <FormField
              label="Добавить существующего пользователя"
              error={duplicate ? duplicateMessage : undefined}
            >
              {(id) => (
                <input
                  id={id}
                  value={identity}
                  onChange={(event) => {
                    setIdentity(event.target.value);
                    setFeedback({});
                  }}
                  placeholder="Логин или рабочая почта"
                  required
                />
              )}
            </FormField>
            <FormField label="Роль">
              {(id) => (
                <select
                  id={id}
                  value={role}
                  aria-describedby={roleHelpId}
                  onChange={(event) => setRole(event.target.value)}
                >
                  {editableRoles.map(([value, label]) => (
                    <option value={value} key={value}>
                      {label}
                    </option>
                  ))}
                </select>
              )}
            </FormField>
            <Button
              type="submit"
              loading={add.isPending}
              disabled={!identity.trim() || duplicate}
              variant="primary"
            >
              <Plus size={15} />
              Добавить
            </Button>
            <p id={roleHelpId} className="gov-project-role-help">
              {roleHelp[role]}
            </p>
            <p className="muted text-sm">
              Доступ к существующим ресурсам и SSH-серверам назначается
              отдельно.
            </p>
          </fieldset>
        </form>
      )}
      {query.isPending ? (
        <LoadingState />
      ) : query.error ? (
        <ErrorState error={query.error} retry={() => void query.refetch()} />
      ) : (
        <DataTable
          rows={query.data.members}
          rowKey={(row) => row.user_id}
          searchValue={(row) => `${row.username} ${row.email}`}
          searchPlaceholder="Найти участника…"
          hideSinglePagePagination
          emptyTitle="В проекте пока нет участников"
          columns={[
            {
              key: "member",
              label: "Участник",
              sortValue: (row) => row.username,
              render: (row) => (
                <span>
                  <strong>{row.username}</strong>
                  <small className="gov-subline">{row.email}</small>
                </span>
              ),
            },
            {
              key: "role",
              label: "Роль",
              render: (row) =>
                project.can_manage && row.role !== "owner" ? (
                  <select
                    aria-label={`Роль ${row.username}`}
                    value={row.role}
                    disabled={pending}
                    onChange={(event) => {
                      if (event.target.value !== row.role) {
                        update.reset();
                        setChangingRole({
                          member: row,
                          role: event.target.value,
                        });
                      }
                    }}
                  >
                    {editableRoles.map(([value, label]) => (
                      <option key={value} value={value}>
                        {label}
                      </option>
                    ))}
                  </select>
                ) : (
                  (roles[row.role] ?? row.role)
                ),
            },
            {
              key: "joined",
              label: "Добавлен",
              sortValue: (row) => Date.parse(row.joined_at) || 0,
              render: (row) => dateTime(row.joined_at),
            },
            ...(project.can_manage &&
            query.data.members.some((member) => member.role !== "owner")
              ? [
                  {
                    key: "actions",
                    label: "Действия",
                    render: (row: ProjectMember) =>
                      row.role !== "owner" ? (
                        <Button
                          variant="ghost"
                          size="icon"
                          disabled={pending}
                          aria-label={`Убрать ${row.username} из проекта`}
                          onClick={() => {
                            remove.reset();
                            setDeleting(row);
                          }}
                        >
                          <Trash2 size={15} />
                        </Button>
                      ) : null,
                  },
                ]
              : []),
          ]}
        />
      )}
      <ConfirmDialog
        open={!!changingRole}
        onOpenChange={(nextOpen) => {
          if (!nextOpen && !update.isPending) setChangingRole(null);
        }}
        title="Изменить роль участника?"
        description={
          changingRole ? (
            <>
              <p>
                «{changingRole.member.username}» получит роль «
                {roles[changingRole.role]}» в проекте «{project.name}».
              </p>
              <p>{roleHelp[changingRole.role]}</p>
              {changingRole.member.user_id === user?.id &&
                changingRole.role !== "admin" && (
                  <p>
                    Вы потеряете возможность управлять участниками этого
                    проекта.
                  </p>
                )}
              <Feedback error={update.error} />
            </>
          ) : (
            ""
          )
        }
        pending={update.isPending}
        confirmLabel="Изменить роль"
        onConfirm={() => {
          if (changingRole && project.can_manage && !pending)
            update.mutate({
              user_id: changingRole.member.user_id,
              role: changingRole.role,
            });
        }}
      />
      <ConfirmDialog
        open={!!deleting}
        onOpenChange={(nextOpen) => {
          if (!nextOpen && !remove.isPending) setDeleting(null);
        }}
        title="Убрать участника из проекта?"
        description={
          <>
            <p>
              «{deleting?.username}» потеряет доступ к проекту «{project.name}».
              Учётная запись сохранится.
            </p>
            <Feedback error={remove.error} />
          </>
        }
        pending={remove.isPending}
        confirmLabel="Убрать участника"
        onConfirm={() => {
          if (deleting && project.can_manage && !pending)
            remove.mutate(deleting.user_id);
        }}
      />
    </div>
  );
}

type ProjectChangeIntent =
  | { type: "activate"; id: string; name: string }
  | { type: "create"; name: string };

export function ProjectSwitcher({
  renderTrigger,
  onOpenChange,
  onCloseAutoFocus,
}: {
  renderTrigger?: (trigger: ReactNode) => ReactNode;
  onOpenChange?: (open: boolean) => void;
  onCloseAutoFocus?: (event: Event) => void;
}) {
  const { user } = useSession();
  const client = useQueryClient();
  const [open, setOpen] = useState(false);
  const [view, setView] = useState<"projects" | "create" | "members">(
    "projects",
  );
  const [name, setName] = useState("");
  const [search, setSearch] = useState("");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [projectChange, setProjectChange] =
    useState<ProjectChangeIntent | null>(null);
  const [projectChangeError, setProjectChangeError] = useState("");
  const memberMutations = useIsMutating({
    mutationKey: ["governance", "project-member-mutation"],
  });
  const projects = useQuery({
    queryKey: ["governance", "projects"],
    queryFn: ({ signal }) => governanceApi.projects(signal),
    enabled: !!user,
  });
  const setDrawerOpen = (nextOpen: boolean) => {
    setOpen(nextOpen);
    onOpenChange?.(nextOpen);
  };
  const resetProjectData = async () => {
    await client.cancelQueries();
    client.removeQueries({
      predicate: (query) =>
        query.queryKey[0] !== "session" &&
        JSON.stringify(query.queryKey) !==
          JSON.stringify(["governance", "projects"]),
    });
    await client.invalidateQueries({ queryKey: ["governance", "projects"] });
    await client.invalidateQueries({ queryKey: ["session"] });
  };
  const activate = useMutation({
    mutationFn: (id: string) => api.post(`/api/projects/${id}/activate/`),
    onSuccess: async () => {
      await resetProjectData();
      setProjectChange(null);
      setDrawerOpen(false);
    },
  });
  const create = useMutation({
    mutationFn: (projectName: string) =>
      api.post("/api/projects/", { name: projectName, activate: true }),
    onSuccess: async () => {
      await resetProjectData();
      setProjectChange(null);
      setName("");
      setView("projects");
      setDrawerOpen(false);
    },
  });
  const pending = activate.isPending || create.isPending || memberMutations > 0;
  const locked = pending || projectChange !== null;
  const pageSaveBlocksChange = () => {
    setProjectChangeError("");
    if (!hasPendingProjectChanges()) return false;
    setProjectChangeError(
      "Дождитесь завершения сохранения на текущей странице.",
    );
    setProjectChange(null);
    return true;
  };
  const performProjectChange = (intent: ProjectChangeIntent) => {
    // A page save may have started after the discard confirmation was opened.
    if (pageSaveBlocksChange()) return;
    if (pending) return;
    if (intent.type === "activate") activate.mutate(intent.id);
    else create.mutate(intent.name);
  };
  const requestProjectChange = (intent: ProjectChangeIntent) => {
    if (pageSaveBlocksChange()) return;
    if (locked) return;
    activate.reset();
    create.reset();
    if (hasUnsavedProjectChanges()) {
      setProjectChange(intent);
      return;
    }
    performProjectChange(intent);
  };
  const changeOpen = (nextOpen: boolean) => {
    if (!nextOpen && locked) return;
    if (nextOpen) {
      setProjectChangeError("");
      setView("projects");
      setSearch("");
      activate.reset();
      create.reset();
      void projects.refetch();
    }
    setDrawerOpen(nextOpen);
  };
  const activeId = projects.data?.active_project_id;
  const active = projects.data?.projects.find(
    (project) => project.id === activeId,
  );
  // Resolve from the refreshed query: a saved Project object would retain
  // can_manage after the current user lowers their own project role.
  const selected = projects.data?.projects.find(
    (project) => project.id === selectedId,
  );
  const visibleProjects = (projects.data?.projects ?? [])
    .filter((project) =>
      project.name
        .toLocaleLowerCase()
        .includes(search.trim().toLocaleLowerCase()),
    )
    .sort(
      (a, b) =>
        Number(b.id === activeId) - Number(a.id === activeId) ||
        a.name.localeCompare(b.name, "ru"),
    );
  const trigger = (
    <Button
      className="gov-project-switcher"
      variant="ghost"
      onClick={() => changeOpen(true)}
      aria-label="Выбрать рабочий проект"
    >
      <Building2 size={17} />
      <span>
        {active?.name ?? user?.active_project?.name ?? "Рабочий проект"}
      </span>
      <ChevronDown size={14} />
    </Button>
  );
  return (
    <>
      {renderTrigger ? renderTrigger(trigger) : trigger}
      <Drawer
        open={open}
        onOpenChange={changeOpen}
        onCloseAutoFocus={onCloseAutoFocus}
        title={
          view === "create"
            ? "Создать проект"
            : view === "members"
              ? "Команда проекта"
              : "Рабочие проекты"
        }
        description={
          view === "create"
            ? "Вы станете владельцем нового проекта. После создания он станет текущим."
            : view === "members"
              ? selected
                ? `${selected.name}. ${selected.id === activeId ? "Текущий проект." : "Просмотр команды не переключает текущий проект."}`
                : "Доступ к участникам выбранного проекта."
              : "Команда, автоматизация и AI-настройки выбранного проекта. Права на SSH-серверы настраиваются отдельно."
        }
        wide
      >
        <div className="gov-project-view" aria-busy={pending}>
          {view !== "projects" && (
            <div className="gov-project-back">
              <Button
                variant="ghost"
                disabled={locked}
                onClick={() => setView("projects")}
              >
                <ArrowLeft size={16} />К проектам
              </Button>
            </div>
          )}
          {view === "projects" && (
            <>
              <Feedback
                error={projectChangeError ? new Error(projectChangeError) : activate.error}
              />
              <div className="gov-project-toolbar">
                <div className="search-field">
                  <Search size={16} />
                  <input
                    aria-label="Найти проект…"
                    placeholder="Найти проект…"
                    value={search}
                    onChange={(event) => setSearch(event.target.value)}
                  />
                  {search && (
                    <button
                      type="button"
                      aria-label="Очистить поиск проектов"
                      onClick={() => setSearch("")}
                    >
                      <X size={14} />
                    </button>
                  )}
                </div>
                <Button
                  disabled={locked}
                  onClick={() => {
                    create.reset();
                    setView("create");
                  }}
                >
                  <Plus size={16} />
                  Создать проект
                </Button>
              </div>
              {projects.isPending ? (
                <LoadingState />
              ) : projects.error ? (
                <ErrorState
                  error={projects.error}
                  retry={() => void projects.refetch()}
                />
              ) : visibleProjects.length ? (
                <div className="gov-project-list">
                  {visibleProjects.map((project) => (
                    <div
                      className={`gov-project-row${project.id === activeId ? " gov-project-row-current" : ""}`}
                      key={project.id}
                    >
                      <Building2 size={20} />
                      <div className="gov-project-summary">
                        <strong>{project.name}</strong>
                        <small>
                          {roles[project.role] ?? project.role} · Участников:{" "}
                          {project.member_count}
                        </small>
                      </div>
                      <div className="gov-project-actions">
                        {project.id === activeId ? (
                          <StatusBadge status="active">
                            Текущий проект
                          </StatusBadge>
                        ) : (
                          <Button
                            size="sm"
                            loading={
                              activate.isPending &&
                              activate.variables === project.id
                            }
                            disabled={locked}
                            onClick={() =>
                              requestProjectChange({
                                type: "activate",
                                id: project.id,
                                name: project.name,
                              })
                            }
                          >
                            Переключить
                          </Button>
                        )}
                        <Button
                          size="sm"
                          disabled={locked}
                          onClick={() => {
                            setSelectedId(project.id);
                            setView("members");
                          }}
                        >
                          Участники
                        </Button>
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <EmptyState
                  title={
                    search.trim() ? "Проекты не найдены" : "Пока нет проектов"
                  }
                  description={
                    search.trim()
                      ? "Попробуйте другое название."
                      : "Создайте проект для совместной работы."
                  }
                />
              )}
            </>
          )}
          {view === "create" && (
            <form
              className="gov-form"
              onSubmit={(event) => {
                event.preventDefault();
                if (name.trim())
                  requestProjectChange({ type: "create", name: name.trim() });
              }}
            >
              <Feedback
                error={projectChangeError ? new Error(projectChangeError) : create.error}
              />
              <fieldset disabled={locked}>
                <FormField
                  label="Название проекта"
                  description="До 120 символов."
                >
                  {(id) => (
                    <input
                      id={id}
                      value={name}
                      onChange={(event) => setName(event.target.value)}
                      maxLength={120}
                      required
                    />
                  )}
                </FormField>
                <div className="gov-row-actions">
                  <Button
                    variant="primary"
                    type="submit"
                    loading={create.isPending}
                    disabled={!name.trim()}
                  >
                    Создать и переключить
                  </Button>
                  <Button
                    onClick={() => {
                      setName("");
                      create.reset();
                      setView("projects");
                    }}
                  >
                    Отмена
                  </Button>
                </div>
              </fieldset>
            </form>
          )}
          {view === "members" &&
            (selected ? (
              <ProjectMembers key={selected.id} project={selected} />
            ) : projects.isPending ? (
              <LoadingState />
            ) : (
              <EmptyState
                title="Проект недоступен"
                description="Возможно, ваш доступ к проекту изменился. Вернитесь к списку проектов."
              />
            ))}
        </div>
        <ConfirmDialog
          open={projectChange !== null}
          onOpenChange={(nextOpen) => {
            if (!nextOpen && !pending) setProjectChange(null);
          }}
          title="Несохранённые изменения"
          description={
            projectChange ? (
              <>
                <p>
                  {projectChange.type === "create"
                    ? `После создания проекта «${projectChange.name}» он станет текущим.`
                    : `Вы перейдёте в проект «${projectChange.name}».`}{" "}
                  Несохранённые изменения на текущей странице будут потеряны.
                </p>
                <Feedback
                  error={
                    projectChange.type === "activate"
                      ? activate.error
                      : create.error
                  }
                />
              </>
            ) : (
              ""
            )
          }
          pending={pending}
          confirmLabel={
            projectChange?.type === "create"
              ? "Не сохранять и создать"
              : "Не сохранять и переключить"
          }
          onConfirm={() => {
            if (projectChange) performProjectChange(projectChange);
          }}
        />
      </Drawer>
    </>
  );
}
