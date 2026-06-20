import { useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";

import {
  ACCESS_FEATURE_OPTIONS,
  createAccessUser,
  deleteAccessUser,
  fetchAccessGroups,
  fetchAccessUsers,
  setAccessUserPassword,
  updateAccessUser,
  type AccessUser,
} from "@/lib/api";
import { ACCESS_UI_TEXT, formatAccessText, localizeAccessFeatures } from "@/lib/accessUiText";
import { useI18n } from "@/lib/i18n";
import { buildExplicitPayload, createPermissionModes } from "./settings-users/accessUserPermissions";
import { SettingsUsersLayout } from "./settings-users/SettingsUsersLayout";
import type { UserCreateForm, UserEditDraft } from "./settings-users/settingsUsersTypes";

const FALLBACK_FEATURES = ACCESS_FEATURE_OPTIONS;

const INITIAL_CREATE_FORM: UserCreateForm = {
  username: "",
  email: "",
  password: "",
  is_staff: false,
  is_active: true,
  access_profile: "server_only",
  groups: [],
};

export default function SettingsUsersPage() {
  const { lang } = useI18n();
  const copy = ACCESS_UI_TEXT[lang].users;
  const queryClient = useQueryClient();
  const [saving, setSaving] = useState(false);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [editing, setEditing] = useState<UserEditDraft>({});
  const [createForm, setCreateForm] = useState<UserCreateForm>(INITIAL_CREATE_FORM);

  const { data: usersData, isLoading, error } = useQuery({
    queryKey: ["access", "users"],
    queryFn: fetchAccessUsers,
  });
  const { data: groupsData } = useQuery({
    queryKey: ["access", "groups"],
    queryFn: fetchAccessGroups,
  });

  const users = useMemo(() => usersData?.users ?? [], [usersData?.users]);
  const groups = useMemo(() => groupsData?.groups ?? [], [groupsData?.groups]);
  const features = useMemo(
    () => localizeAccessFeatures(lang, usersData?.features ?? groupsData?.features ?? FALLBACK_FEATURES),
    [groupsData?.features, lang, usersData?.features],
  );

  const refreshAll = async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ["access", "users"] }),
      queryClient.invalidateQueries({ queryKey: ["access", "groups"] }),
      queryClient.invalidateQueries({ queryKey: ["access", "permissions"] }),
      queryClient.invalidateQueries({ queryKey: ["access", "group-permissions"] }),
    ]);
  };

  const startEdit = (user: AccessUser) => {
    setEditingId(user.id);
    setEditing({
      username: user.username,
      email: user.email,
      is_staff: user.is_staff,
      is_active: user.is_active,
      access_profile: user.access_profile || "custom",
      groups: (user.groups || []).map((group) => group.id),
      permission_modes: createPermissionModes(features, user.explicit_permissions),
    });
  };

  const cancelEdit = () => {
    setEditingId(null);
    setEditing({});
  };

  const createUser = async () => {
    setSaving(true);
    try {
      await createAccessUser({ ...createForm });
      setCreateForm(INITIAL_CREATE_FORM);
      await refreshAll();
    } finally {
      setSaving(false);
    }
  };

  const saveEdit = async () => {
    if (!editingId) return;
    setSaving(true);
    try {
      await updateAccessUser(editingId, {
        username: editing.username,
        email: editing.email,
        is_staff: editing.is_staff,
        is_active: editing.is_active,
        access_profile: editing.access_profile,
        groups: editing.groups ?? [],
        explicit_permissions: buildExplicitPayload(editing.permission_modes ?? {}),
      });
      cancelEdit();
      await refreshAll();
    } finally {
      setSaving(false);
    }
  };

  const removeUser = async (user: AccessUser) => {
    if (!confirm(formatAccessText(copy.deleteConfirm, { name: user.username }))) return;
    await deleteAccessUser(user.id);
    await refreshAll();
  };

  const resetPassword = async (user: AccessUser) => {
    const password = prompt(formatAccessText(copy.passwordPrompt, { name: user.username }));
    if (!password) return;
    await setAccessUserPassword(user.id, password);
    alert(copy.passwordUpdated);
  };

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-20">
        <div className="h-6 w-6 animate-spin rounded-full border-2 border-primary border-t-transparent" />
      </div>
    );
  }

  if (error) {
    return <div className="p-6 text-sm text-destructive">{copy.error}</div>;
  }

  return (
    <SettingsUsersLayout
      lang={lang}
      users={users}
      groups={groups}
      features={features}
      saving={saving}
      editingId={editingId}
      editing={editing}
      createForm={createForm}
      onStartEdit={startEdit}
      onCancelEdit={cancelEdit}
      onSaveEdit={saveEdit}
      onRemoveUser={removeUser}
      onResetPassword={resetPassword}
      onCreateUser={createUser}
      onEditingChange={setEditing}
      onCreateFormChange={setCreateForm}
    />
  );
}
