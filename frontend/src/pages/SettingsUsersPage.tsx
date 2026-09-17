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
import { QueryStateBlock } from "@/components/ui/page-shell";
import { SkeletonTable } from "@/components/ui/list-state";
import { DeleteDialog } from "@/components/system/ConfirmDialog";
import { useI18n } from "@/lib/i18n";
import { notify } from "@/lib/notify";
import { buildExplicitPayload, createPermissionModes } from "./settings-users/accessUserPermissions";
import { SettingsUsersLayout } from "./settings-users/SettingsUsersLayout";
import { ResetPasswordDialog } from "./settings-users/UserSecurityDialogs";
import type { UserCreateForm, UserEditDraft } from "./settings-users/settingsUsersTypes";
import { validateCreateUserForm, validateEditUserDraft } from "./settings-users/userValidation";

const FALLBACK_FEATURES = ACCESS_FEATURE_OPTIONS;

const INITIAL_CREATE_FORM: UserCreateForm = {
  username: "",
  email: "",
  password: "",
  is_staff: false,
  is_active: true,
  access_profile: "pilot_user",
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
  const [deleteTarget, setDeleteTarget] = useState<AccessUser | null>(null);
  const [passwordTarget, setPasswordTarget] = useState<AccessUser | null>(null);

  const { data: usersData, isLoading, error, refetch } = useQuery({
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
  const createValidation = useMemo(() => validateCreateUserForm(createForm, lang), [createForm, lang]);
  const editValidation = useMemo(() => validateEditUserDraft(editing, lang), [editing, lang]);

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
    if (!createValidation.isValid) {
      notify.error({ title: copy.createTitle, description: createValidation.summary });
      return false;
    }

    setSaving(true);
    try {
      await createAccessUser({ ...createForm });
      setCreateForm({ ...INITIAL_CREATE_FORM });
      await refreshAll();
      return true;
    } catch (err) {
      notify.error({ title: copy.createTitle, description: err instanceof Error ? err.message : String(err) });
      return false;
    } finally {
      setSaving(false);
    }
  };

  const saveEdit = async () => {
    if (!editingId) return false;
    if (!editValidation.isValid) {
      notify.error({ title: copy.editAction, description: editValidation.summary });
      return false;
    }

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
      return true;
    } catch (err) {
      notify.error({ title: copy.editAction, description: err instanceof Error ? err.message : String(err) });
      return false;
    } finally {
      setSaving(false);
    }
  };

  const removeUser = async (user: AccessUser) => {
    setDeleteTarget(user);
  };

  const resetPassword = async (user: AccessUser) => {
    setPasswordTarget(user);
  };

  const confirmRemoveUser = async () => {
    if (!deleteTarget) return;
    setSaving(true);
    try {
      await deleteAccessUser(deleteTarget.id);
      notify.success({ title: copy.deleteAction, description: deleteTarget.username });
      setDeleteTarget(null);
      await refreshAll();
    } catch (err) {
      notify.error({ title: copy.error, description: err instanceof Error ? err.message : String(err) });
    } finally {
      setSaving(false);
    }
  };

  const submitResetPassword = async (password: string) => {
    if (!passwordTarget) return;
    setSaving(true);
    try {
      await setAccessUserPassword(passwordTarget.id, password);
      notify.success({ title: copy.passwordUpdated, description: passwordTarget.username });
      setPasswordTarget(null);
      await refreshAll();
    } catch (err) {
      notify.error({ title: copy.error, description: err instanceof Error ? err.message : String(err) });
    } finally {
      setSaving(false);
    }
  };

  if (isLoading) {
    return <div className="p-6"><SkeletonTable rows={8} cols={4} /></div>;
  }

  if (error) {
    return (
      <div className="p-6">
        <QueryStateBlock error={error} errorText={copy.error} onRetry={() => void refetch()}>
          {null}
        </QueryStateBlock>
      </div>
    );
  }

  return (
    <>
      <SettingsUsersLayout
        lang={lang}
        users={users}
        groups={groups}
        features={features}
        saving={saving}
        editingId={editingId}
        editing={editing}
        createForm={createForm}
        createValidation={createValidation}
        editValidation={editValidation}
        onStartEdit={startEdit}
        onCancelEdit={cancelEdit}
        onSaveEdit={saveEdit}
        onRemoveUser={removeUser}
        onResetPassword={resetPassword}
        onCreateUser={createUser}
        onEditingChange={setEditing}
        onCreateFormChange={setCreateForm}
      />
      <DeleteDialog
        open={Boolean(deleteTarget)}
        onOpenChange={(open) => {
          if (!open && !saving) setDeleteTarget(null);
        }}
        title={formatAccessText(copy.deleteConfirm, { name: deleteTarget?.username || "" })}
        description={formatAccessText(copy.deleteDescription, { name: deleteTarget?.username || "" })}
        confirmLabel={copy.deleteAction}
        cancelLabel={ACCESS_UI_TEXT[lang].common.cancel}
        onConfirm={confirmRemoveUser}
      />
      <ResetPasswordDialog
        lang={lang}
        user={passwordTarget}
        open={Boolean(passwordTarget)}
        saving={saving}
        onOpenChange={(open) => {
          if (!open && !saving) setPasswordTarget(null);
        }}
        onSubmit={submitResetPassword}
      />
    </>
  );
}
