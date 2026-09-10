import { useState } from "react";
import { useForm, useWatch } from "react-hook-form";
import { useQuery } from "@tanstack/react-query";
import { KeyRound, Plus, ShieldCheck, Trash2, Users } from "lucide-react";
import { api } from "@/api/client";
import {
  governanceApi,
  type AccessGroup,
  type AccessPermission,
  type AccessUser,
  type FeatureChoice,
  type PermissionMap,
} from "@/api/governance";
import { useSession } from "@/app/session";
import {
  Button,
  ConfirmDialog,
  DataTable,
  Drawer,
  ErrorState,
  Feedback,
  LoadingState,
  PageHeader,
  Panel,
  StatusBadge,
  Tabs,
} from "@/components/ui";
import {
  CheckField,
  FormField,
  GovernanceGuard,
  PermissionEditor,
  dateTime,
  featureLabels,
  profileLabels,
  useGovernanceMutation,
} from "./shared";

interface UserForm {
  username: string;
  email: string;
  password: string;
  is_active: boolean;
  is_staff: boolean;
  access_profile: string;
}
function UserEditor({
  user,
  features,
  groups,
  onClose,
}: {
  user: AccessUser | null;
  features: FeatureChoice[];
  groups: AccessGroup[];
  onClose: () => void;
}) {
  const { user: session } = useSession();
  const [tab, setTab] = useState("identity");
  const [selectedGroups, setSelectedGroups] = useState(
    user?.groups.map((g) => g.id) ?? [],
  );
  const [permissions, setPermissions] = useState<PermissionMap>(
    user?.explicit_permissions ?? {},
  );
  const [password, setPassword] = useState("");
  const form = useForm<UserForm>({
    defaultValues: {
      username: user?.username ?? "",
      email: user?.email ?? "",
      password: "",
      is_active: user?.is_active ?? true,
      is_staff: user?.is_staff ?? false,
      access_profile: user?.access_profile ?? "pilot_user",
    },
  });
  const watched = useWatch({ control: form.control });
  const locked = !!user?.is_superuser && user.id !== session?.id;
  const save = useGovernanceMutation(async (values: UserForm) => {
    const payload = {
      ...values,
      groups: selectedGroups,
      explicit_permissions: permissions,
    };
    if (user) {
      delete (payload as Partial<UserForm>).password;
      return api.put(`/api/access/users/${user.id}/`, payload);
    }
    return api.post("/api/access/users/", payload);
  }, onClose);
  const passwordSave = useGovernanceMutation(
    () => api.post(`/api/access/users/${user!.id}/password/`, { password }),
    () => setPassword(""),
  );
  const close = () => {
    if (save.isPending || passwordSave.isPending) return;
    if (
      form.formState.isDirty ||
      JSON.stringify(permissions) !==
        JSON.stringify(user?.explicit_permissions ?? {}) ||
      selectedGroups.join(",") !==
        (user?.groups.map((g) => g.id) ?? []).join(",")
    ) {
      if (!window.confirm("Закрыть без сохранения изменений?")) return;
    }
    onClose();
  };
  return (
    <Drawer
      open
      onOpenChange={(open) => {
        if (!open) close();
      }}
      title={user ? user.username : "Новый пользователь"}
      description={
        user
          ? "Учётная запись, группы и правила доступа."
          : "Пользователь получит доступ после создания учётной записи."
      }
      wide
      footer={
        tab !== "password" && (
          <>
            <Button onClick={close}>Отмена</Button>
            <Button
              variant="primary"
              disabled={locked}
              loading={save.isPending}
              onClick={() =>
                void form.handleSubmit((values) => save.mutate(values))()
              }
            >
              Сохранить
            </Button>
          </>
        )
      }
    >
      <Feedback error={save.error} />
      {locked && (
        <div className="notice">
          Учётную запись суперпользователя может изменять только её владелец.
        </div>
      )}
      <Tabs
        items={[
          { value: "identity", label: "Учётная запись" },
          { value: "permissions", label: "Права доступа" },
          ...(user ? [{ value: "password", label: "Пароль" }] : []),
        ]}
        value={tab}
        onChange={setTab}
      />
      {tab === "identity" && (
        <form
          className="gov-form"
          onSubmit={form.handleSubmit((values) => save.mutate(values))}
        >
          <fieldset disabled={locked || save.isPending}>
            <FormField
              label="Имя пользователя"
              error={form.formState.errors.username?.message}
            >
              {(id) => (
                <input
                  id={id}
                  autoComplete="username"
                  {...form.register("username", {
                    required: "Укажите имя пользователя",
                    maxLength: { value: 150, message: "До 150 символов" },
                  })}
                />
              )}
            </FormField>
            <FormField
              label="Рабочая почта"
              error={form.formState.errors.email?.message}
            >
              {(id) => (
                <input
                  id={id}
                  type="email"
                  autoComplete="email"
                  {...form.register("email")}
                />
              )}
            </FormField>
            {!user && (
              <FormField
                label="Начальный пароль"
                error={form.formState.errors.password?.message}
              >
                {(id) => (
                  <input
                    id={id}
                    type="password"
                    autoComplete="new-password"
                    {...form.register("password", {
                      required: "Укажите пароль",
                      minLength: {
                        value: 12,
                        message: "Используйте не менее 12 символов",
                      },
                    })}
                  />
                )}
              </FormField>
            )}
            <FormField
              label="Профиль доступа"
              description="Выбор профиля назначает разрешения и роль администратора."
            >
              {(id) => (
                <select
                  id={id}
                  {...form.register("access_profile")}
                  onChange={(e) => {
                    form.setValue("access_profile", e.target.value, {
                      shouldDirty: true,
                    });
                    setPermissions({});
                  }}
                >
                  {Object.entries(profileLabels).map(([value, label]) => (
                    <option key={value} value={value}>
                      {label}
                    </option>
                  ))}
                </select>
              )}
            </FormField>
            <CheckField
              label="Учётная запись активна"
              checked={!!watched.is_active}
              onChange={(value) =>
                form.setValue("is_active", value, { shouldDirty: true })
              }
            />
            {watched.access_profile === "custom" && (
              <CheckField
                label="Администратор"
                description="Административные действия также требуют соответствующих прав."
                checked={!!watched.is_staff}
                onChange={(value) =>
                  form.setValue("is_staff", value, { shouldDirty: true })
                }
              />
            )}
            <div className="field">
              <label>Группы доступа</label>
              {groups.length ? (
                <div className="gov-check-list">
                  {groups.map((group) => (
                    <CheckField
                      key={group.id}
                      label={group.name}
                      checked={selectedGroups.includes(group.id)}
                      onChange={(checked) =>
                        setSelectedGroups((current) =>
                          checked
                            ? [...current, group.id]
                            : current.filter((id) => id !== group.id),
                        )
                      }
                    />
                  ))}
                </div>
              ) : (
                <p className="muted">Группы ещё не созданы.</p>
              )}
            </div>
            {user?.date_joined && (
              <p className="muted text-sm">
                Создана {dateTime(user.date_joined)}
              </p>
            )}
          </fieldset>
        </form>
      )}
      {tab === "permissions" && (
        <fieldset disabled={locked || save.isPending}>
          <p className="muted text-sm">
            Личное правило имеет приоритет над правилами групп. «Наследовать»
            удаляет личное правило.
          </p>
          <PermissionEditor
            features={features}
            value={permissions}
            onChange={(value) => {
              setPermissions(value);
              form.setValue("access_profile", "custom", { shouldDirty: true });
            }}
            effective={user?.effective_permissions}
            sources={user?.permission_sources}
          />
        </fieldset>
      )}
      {tab === "password" && (
        <form
          className="gov-form"
          onSubmit={(e) => {
            e.preventDefault();
            passwordSave.mutate();
          }}
        >
          <Feedback error={passwordSave.error} success={passwordSave.message} />
          <p className="muted">
            Смена пароля завершит ранее открытые сессии пользователя после
            следующей проверки.
          </p>
          <FormField label="Новый пароль" description="Не менее 12 символов.">
            {(id) => (
              <input
                id={id}
                type="password"
                autoComplete="new-password"
                minLength={12}
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                disabled={locked}
              />
            )}
          </FormField>
          <Button
            type="submit"
            variant="primary"
            loading={passwordSave.isPending}
            disabled={locked || password.length < 12}
          >
            <KeyRound size={16} />
            Обновить пароль
          </Button>
        </form>
      )}
    </Drawer>
  );
}
function UsersContent() {
  const { user: session } = useSession();
  const users = useQuery({
    queryKey: ["governance", "users"],
    queryFn: ({ signal }) => governanceApi.users(signal),
  });
  const groups = useQuery({
    queryKey: ["governance", "groups"],
    queryFn: ({ signal }) => governanceApi.groups(signal),
  });
  const [editing, setEditing] = useState<AccessUser | null | undefined>(
    undefined,
  );
  const [deleting, setDeleting] = useState<AccessUser | null>(null);
  const remove = useGovernanceMutation(
    (id: number) => api.delete(`/api/access/users/${id}/`),
    () => setDeleting(null),
  );
  return (
    <>
      <PageHeader
        eyebrow="Управление доступом"
        title="Пользователи"
        description="Учётные записи и эффективный доступ к рабочим пространствам."
        actions={
          <Button variant="primary" onClick={() => setEditing(null)}>
            <Plus size={16} />
            Добавить пользователя
          </Button>
        }
      />
      <Feedback error={remove.error} success={remove.message} />
      {users.isPending ? (
        <LoadingState />
      ) : users.error ? (
        <ErrorState error={users.error} retry={() => void users.refetch()} />
      ) : (
        <Panel>
          <DataTable
            rows={users.data.users}
            rowKey={(row) => row.id}
            searchValue={(row) =>
              `${row.username} ${row.email} ${row.groups.map((g) => g.name).join(" ")}`
            }
            searchPlaceholder="Найти пользователя или группу"
            emptyTitle="Пользователей пока нет"
            columns={[
              {
                key: "user",
                label: "Пользователь",
                sortValue: (row) => row.username,
                render: (row) => (
                  <button
                    className="gov-identity"
                    onClick={() => setEditing(row)}
                  >
                    <span className="gov-avatar">
                      {row.username.slice(0, 2).toUpperCase()}
                    </span>
                    <span>
                      <strong>
                        {row.username}
                        {row.id === session?.id && (
                          <small className="gov-you">Вы</small>
                        )}
                      </strong>
                      <small>{row.email || "Почта не указана"}</small>
                    </span>
                  </button>
                ),
              },
              {
                key: "role",
                label: "Профиль",
                sortValue: (row) => row.access_profile,
                render: (row) => (
                  <span>
                    {profileLabels[row.access_profile] ?? row.access_profile}
                    {row.is_superuser && (
                      <small className="gov-subline">Суперпользователь</small>
                    )}
                  </span>
                ),
              },
              {
                key: "groups",
                label: "Группы",
                render: (row) => (
                  <div className="gov-chips">
                    {row.groups.length ? (
                      row.groups.map((g) => (
                        <span className="gov-chip" key={g.id}>
                          {g.name}
                        </span>
                      ))
                    ) : (
                      <span className="muted">Без группы</span>
                    )}
                  </div>
                ),
              },
              {
                key: "status",
                label: "Состояние",
                sortValue: (row) => Number(row.is_active),
                render: (row) => (
                  <StatusBadge status={row.is_active ? "active" : "disabled"} />
                ),
              },
              {
                key: "action",
                label: "Действия",
                render: (row) => (
                  <div className="gov-row-actions">
                    <Button size="sm" onClick={() => setEditing(row)}>
                      Настроить
                    </Button>
                    <Button
                      size="icon"
                      variant="ghost"
                      aria-label={`Удалить ${row.username}`}
                      disabled={row.id === session?.id || row.is_superuser}
                      onClick={() => setDeleting(row)}
                    >
                      <Trash2 size={15} />
                    </Button>
                  </div>
                ),
              },
            ]}
          />
        </Panel>
      )}
      {editing !== undefined &&
        (groups.error ? (
          <ErrorState
            error={groups.error}
            retry={() => void groups.refetch()}
          />
        ) : groups.isPending ? (
          <LoadingState />
        ) : (
          <UserEditor
            key={editing?.id ?? "new"}
            user={editing}
            groups={groups.data.groups}
            features={users.data?.features ?? groups.data.features}
            onClose={() => setEditing(undefined)}
          />
        ))}
      <ConfirmDialog
        open={!!deleting}
        onOpenChange={(open) => {
          if (!open) setDeleting(null);
        }}
        title="Удалить пользователя?"
        description={`Учётная запись «${deleting?.username}» и связанные с ней данные будут удалены. Это действие нельзя отменить.`}
        typedText={deleting?.username}
        pending={remove.isPending}
        confirmLabel="Удалить пользователя"
        onConfirm={() => deleting && remove.mutate(deleting.id)}
      />
    </>
  );
}
export function UsersPage() {
  return (
    <GovernanceGuard staff>
      <UsersContent />
    </GovernanceGuard>
  );
}

function GroupEditor({
  group,
  users,
  features,
  onClose,
}: {
  group: AccessGroup | null;
  users: AccessUser[];
  features: FeatureChoice[];
  onClose: () => void;
}) {
  const [name, setName] = useState(group?.name ?? "");
  const [members, setMembers] = useState(
    group?.members.map((member) => member.id) ?? [],
  );
  const [permissions, setPermissions] = useState<PermissionMap>(
    group?.explicit_permissions ?? {},
  );
  const [tab, setTab] = useState("members");
  const save = useGovernanceMutation(
    () =>
      group
        ? api.put(`/api/access/groups/${group.id}/`, {
            name,
            members,
            explicit_permissions: permissions,
          })
        : api.post("/api/access/groups/", {
            name,
            members,
            explicit_permissions: permissions,
          }),
    onClose,
  );
  return (
    <Drawer
      open
      onOpenChange={(open) => {
        if (!open && !save.isPending) onClose();
      }}
      title={group ? group.name : "Новая группа"}
      description="Участники группы наследуют её правила доступа."
      wide
      footer={
        <>
          <Button onClick={onClose}>Отмена</Button>
          <Button
            variant="primary"
            loading={save.isPending}
            disabled={!name.trim()}
            onClick={() => save.mutate()}
          >
            Сохранить группу
          </Button>
        </>
      }
    >
      <Feedback error={save.error} />
      <FormField label="Название группы">
        {(id) => (
          <input
            id={id}
            value={name}
            maxLength={150}
            onChange={(e) => setName(e.target.value)}
            required
          />
        )}
      </FormField>
      <Tabs
        items={[
          { value: "members", label: "Участники", count: members.length },
          { value: "permissions", label: "Права доступа" },
        ]}
        value={tab}
        onChange={setTab}
      />
      {tab === "members" ? (
        <DataTable
          rows={users}
          rowKey={(row) => row.id}
          searchValue={(row) => `${row.username} ${row.email}`}
          emptyTitle="Нет доступных пользователей"
          columns={[
            {
              key: "member",
              label: "Участник",
              render: (row) => (
                <CheckField
                  label={row.username}
                  description={row.email}
                  checked={members.includes(row.id)}
                  onChange={(checked) =>
                    setMembers((current) =>
                      checked
                        ? [...current, row.id]
                        : current.filter((id) => id !== row.id),
                    )
                  }
                />
              ),
            },
          ]}
        />
      ) : (
        <>
          <p className="muted text-sm">
            Если хотя бы одна группа запрещает функцию, её групповой доступ
            будет запрещён. Личное правило пользователя имеет приоритет.
          </p>
          <PermissionEditor
            features={features}
            value={permissions}
            onChange={setPermissions}
          />
        </>
      )}
    </Drawer>
  );
}
function GroupsContent() {
  const groups = useQuery({
    queryKey: ["governance", "groups"],
    queryFn: ({ signal }) => governanceApi.groups(signal),
  });
  const users = useQuery({
    queryKey: ["governance", "users"],
    queryFn: ({ signal }) => governanceApi.users(signal),
  });
  const [editing, setEditing] = useState<AccessGroup | null | undefined>();
  const [deleting, setDeleting] = useState<AccessGroup | null>(null);
  const remove = useGovernanceMutation(
    (id: number) => api.delete(`/api/access/groups/${id}/`),
    () => setDeleting(null),
  );
  return (
    <>
      <PageHeader
        eyebrow="Управление доступом"
        title="Группы доступа"
        description="Назначайте права командам и управляйте составом в одном месте."
        actions={
          <Button variant="primary" onClick={() => setEditing(null)}>
            <Plus size={16} />
            Создать группу
          </Button>
        }
      />
      <Feedback error={remove.error} success={remove.message} />
      {groups.isPending ? (
        <LoadingState />
      ) : groups.error ? (
        <ErrorState error={groups.error} retry={() => void groups.refetch()} />
      ) : (
        <Panel>
          <DataTable
            rows={groups.data.groups}
            rowKey={(row) => row.id}
            searchValue={(row) =>
              `${row.name} ${row.members.map((m) => m.username).join(" ")}`
            }
            emptyTitle="Создайте первую группу"
            emptyDescription="Группы помогают назначать согласованный доступ участникам команды."
            emptyAction={
              <Button onClick={() => setEditing(null)}>
                <Plus size={16} />
                Создать группу
              </Button>
            }
            columns={[
              {
                key: "name",
                label: "Группа",
                sortValue: (row) => row.name,
                render: (row) => (
                  <button
                    className="gov-identity"
                    onClick={() => setEditing(row)}
                  >
                    <span className="gov-avatar">
                      <Users size={18} />
                    </span>
                    <strong>{row.name}</strong>
                  </button>
                ),
              },
              {
                key: "members",
                label: "Участники",
                sortValue: (row) => row.member_count ?? row.members.length,
                render: (row) => (
                  <span>
                    {row.member_count ?? row.members.length}
                    <small className="gov-subline">
                      {row.members
                        .slice(0, 3)
                        .map((m) => m.username)
                        .join(", ")}
                    </small>
                  </span>
                ),
              },
              {
                key: "permissions",
                label: "Правила",
                render: (row) =>
                  `${Object.values(row.explicit_permissions).filter((v) => v === true).length} разрешено · ${Object.values(row.explicit_permissions).filter((v) => v === false).length} запрещено`,
              },
              {
                key: "actions",
                label: "Действия",
                render: (row) => (
                  <div className="gov-row-actions">
                    <Button size="sm" onClick={() => setEditing(row)}>
                      Настроить
                    </Button>
                    <Button
                      size="icon"
                      variant="ghost"
                      aria-label={`Удалить группу ${row.name}`}
                      onClick={() => setDeleting(row)}
                    >
                      <Trash2 size={15} />
                    </Button>
                  </div>
                ),
              },
            ]}
          />
        </Panel>
      )}
      {editing !== undefined &&
        (users.error ? (
          <ErrorState error={users.error} retry={() => void users.refetch()} />
        ) : users.isPending ? (
          <LoadingState />
        ) : (
          <GroupEditor
            group={editing}
            users={users.data.users}
            features={groups.data?.features ?? users.data.features}
            onClose={() => setEditing(undefined)}
          />
        ))}
      <ConfirmDialog
        open={!!deleting}
        onOpenChange={(open) => {
          if (!open) setDeleting(null);
        }}
        title="Удалить группу доступа?"
        description={`Группа «${deleting?.name}» и её правила будут удалены. Участники сохранят учётные записи, их эффективный доступ будет пересчитан.`}
        typedText={deleting?.name}
        pending={remove.isPending}
        onConfirm={() => deleting && remove.mutate(deleting.id)}
        confirmLabel="Удалить группу"
      />
    </>
  );
}
export function GroupsPage() {
  return (
    <GovernanceGuard staff>
      <GroupsContent />
    </GovernanceGuard>
  );
}

function PermissionsContent() {
  const query = useQuery({
    queryKey: ["governance", "permissions"],
    queryFn: ({ signal }) => governanceApi.permissions(signal),
  });
  const users = useQuery({
    queryKey: ["governance", "users"],
    queryFn: ({ signal }) => governanceApi.users(signal),
  });
  const groups = useQuery({
    queryKey: ["governance", "groups"],
    queryFn: ({ signal }) => governanceApi.groups(signal),
  });
  const [tab, setTab] = useState("users");
  const [create, setCreate] = useState(false);
  const [principal, setPrincipal] = useState("");
  const [feature, setFeature] = useState("");
  const [allowed, setAllowed] = useState(true);
  const [deleting, setDeleting] = useState<AccessPermission | null>(null);
  const path = tab === "users" ? "permissions" : "group-permissions";
  const save = useGovernanceMutation(
    () =>
      api.post(`/api/access/${path}/`, {
        [tab === "users" ? "user_id" : "group_id"]: Number(principal),
        feature,
        allowed,
      }),
    () => setCreate(false),
  );
  const remove = useGovernanceMutation(
    (id: number) => api.delete(`/api/access/${path}/${id}/`),
    () => setDeleting(null),
  );
  const update = useGovernanceMutation(
    ({ id, allow }: { id: number; allow: boolean }) =>
      api.put(`/api/access/${path}/${id}/`, { allowed: allow }),
  );
  return (
    <>
      <PageHeader
        eyebrow="Управление доступом"
        title="Правила и разрешения"
        description="Явные назначения пользователей и групп. Удаление правила возвращает наследование."
        actions={
          <Button
            variant="primary"
            onClick={() => {
              setPrincipal("");
              setFeature("");
              setAllowed(true);
              setCreate(true);
            }}
          >
            <Plus size={16} />
            Назначить право
          </Button>
        }
      />
      <Feedback
        error={remove.error ?? update.error}
        success={remove.message || update.message}
      />
      <Tabs
        items={[
          {
            value: "users",
            label: "Личные правила",
            count: query.data?.permissions.length,
          },
          {
            value: "groups",
            label: "Правила групп",
            count: query.data?.group_permissions.length,
          },
        ]}
        value={tab}
        onChange={(value) => {
          setTab(value);
          setDeleting(null);
        }}
      />
      {query.isPending ? (
        <LoadingState />
      ) : query.error ? (
        <ErrorState error={query.error} retry={() => void query.refetch()} />
      ) : (
        <Panel>
          <DataTable
            rows={
              tab === "users"
                ? query.data.permissions
                : query.data.group_permissions
            }
            rowKey={(row) => row.id}
            searchValue={(row) =>
              `${row.username ?? row.group_name} ${featureLabels[row.feature] ?? row.feature}`
            }
            emptyTitle="Явных правил нет"
            emptyDescription="Доступ определяется профилями и наследованием."
            columns={[
              {
                key: "principal",
                label: tab === "users" ? "Пользователь" : "Группа",
                sortValue: (row) => row.username ?? row.group_name ?? "",
                render: (row) => (
                  <strong>{row.username ?? row.group_name}</strong>
                ),
              },
              {
                key: "feature",
                label: "Функция",
                sortValue: (row) => row.feature,
                render: (row) =>
                  featureLabels[row.feature] ??
                  row.feature_display ??
                  row.feature,
              },
              {
                key: "allow",
                label: "Доступ",
                render: (row) => (
                  <select
                    aria-label={`Доступ к ${row.feature} для ${row.username ?? row.group_name}`}
                    value={row.allowed ? "allow" : "deny"}
                    disabled={update.isPending}
                    onChange={(e) =>
                      update.mutate({
                        id: row.id,
                        allow: e.target.value === "allow",
                      })
                    }
                  >
                    <option value="allow">Разрешить</option>
                    <option value="deny">Запретить</option>
                  </select>
                ),
              },
              {
                key: "remove",
                label: "Действие",
                render: (row) => (
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={() => setDeleting(row)}
                  >
                    Восстановить наследование
                  </Button>
                ),
              },
            ]}
          />
        </Panel>
      )}
      <Drawer
        open={create}
        onOpenChange={setCreate}
        title="Назначить право"
        description="Правило действует сразу после сохранения."
        footer={
          <>
            <Button onClick={() => setCreate(false)}>Отмена</Button>
            <Button
              variant="primary"
              disabled={!principal || !feature}
              loading={save.isPending}
              onClick={() => save.mutate()}
            >
              Назначить
            </Button>
          </>
        }
      >
        <Feedback error={save.error} />
        <div className="gov-form">
          <FormField label={tab === "users" ? "Пользователь" : "Группа"}>
            {(id) => (
              <select
                id={id}
                value={principal}
                onChange={(e) => setPrincipal(e.target.value)}
              >
                <option value="">Выберите получателя</option>
                {tab === "users"
                  ? users.data?.users.map((u) => (
                      <option key={u.id} value={u.id}>
                        {u.username}
                      </option>
                    ))
                  : groups.data?.groups.map((g) => (
                      <option key={g.id} value={g.id}>
                        {g.name}
                      </option>
                    ))}
              </select>
            )}
          </FormField>
          <FormField label="Функция">
            {(id) => (
              <select
                id={id}
                value={feature}
                onChange={(e) => setFeature(e.target.value)}
              >
                <option value="">Выберите функцию</option>
                {query.data?.features.map((f) => (
                  <option key={f.value} value={f.value}>
                    {featureLabels[f.value] ?? f.label}
                  </option>
                ))}
              </select>
            )}
          </FormField>
          <FormField label="Правило">
            {(id) => (
              <select
                id={id}
                value={allowed ? "allow" : "deny"}
                onChange={(e) => setAllowed(e.target.value === "allow")}
              >
                <option value="allow">Разрешить</option>
                <option value="deny">Запретить</option>
              </select>
            )}
          </FormField>
          {(users.error || groups.error) && (
            <ErrorState error={users.error ?? groups.error} />
          )}
        </div>
      </Drawer>
      <ConfirmDialog
        open={!!deleting}
        onOpenChange={(open) => {
          if (!open) setDeleting(null);
        }}
        title="Восстановить наследование?"
        description={`Правило «${featureLabels[deleting?.feature ?? ""] ?? deleting?.feature}» для ${deleting?.username ?? deleting?.group_name} будет удалено. Доступ определят оставшиеся правила.`}
        pending={remove.isPending}
        onConfirm={() => deleting && remove.mutate(deleting.id)}
        confirmLabel="Удалить правило"
      />
    </>
  );
}
export function PermissionsPage() {
  return (
    <GovernanceGuard staff>
      <PermissionsContent />
    </GovernanceGuard>
  );
}

export function AccessOverview() {
  return (
    <GovernanceGuard staff>
      <PageHeader
        eyebrow="Управление доступом"
        title="Политика доступа"
        description="Права вычисляются на сервере по индивидуальным назначениям, группам и профилям."
      />
      <div className="gov-policy-grid">
        {[
          {
            title: "Пользователи",
            href: "/governance/users",
            text: "Учётные записи, профиль доступа и личные правила.",
            icon: <Users size={23} />,
          },
          {
            title: "Группы",
            href: "/governance/groups",
            text: "Состав команд и общие права участников.",
            icon: <ShieldCheck size={23} />,
          },
          {
            title: "Разрешения",
            href: "/governance/permissions",
            text: "Все явные назначения и восстановление наследования.",
            icon: <KeyRound size={23} />,
          },
        ].map((item) => (
          <a className="gov-policy-card" href={item.href} key={item.href}>
            {item.icon}
            <h2>{item.title}</h2>
            <p>{item.text}</p>
            <span>Открыть →</span>
          </a>
        ))}
      </div>
      <Panel title="Порядок применения правил">
        <ol className="gov-policy-order">
          <li>Ограничения развёртывания</li>
          <li>Личное правило пользователя</li>
          <li>Правила групп: запрет имеет приоритет</li>
          <li>Профиль и базовые разрешения</li>
        </ol>
        <p className="muted">
          AI-маршрутизация и критические возможности требуют отдельного
          назначения. Роль администратора сама по себе их не открывает.
        </p>
      </Panel>
    </GovernanceGuard>
  );
}
