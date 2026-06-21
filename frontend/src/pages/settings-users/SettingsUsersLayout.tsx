import { useState, type Dispatch, type SetStateAction } from "react";
import { UserPlus, Users as UsersIcon } from "lucide-react";

import type { AccessUser } from "@/lib/api";
import { ACCESS_UI_TEXT } from "@/lib/accessUiText";
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { CreateUserSidebar } from "./CreateUserSidebar";
import { UserDirectory } from "./UserDirectory";
import type {
  AccessFeatureOption,
  AccessGroupOption,
  UserCreateForm,
  UserEditDraft,
} from "./settingsUsersTypes";
import type { UserValidationResult } from "./userValidation";

type AsyncAction = () => boolean | Promise<boolean>;
type AsyncUserAction = (user: AccessUser) => void | Promise<void>;

type SettingsUsersLayoutProps = {
  lang: "en" | "ru";
  users: AccessUser[];
  groups: AccessGroupOption[];
  features: AccessFeatureOption[];
  saving: boolean;
  editingId: number | null;
  editing: UserEditDraft;
  createForm: UserCreateForm;
  createValidation: UserValidationResult;
  editValidation: UserValidationResult;
  onStartEdit: (user: AccessUser) => void;
  onCancelEdit: () => void;
  onSaveEdit: AsyncAction;
  onRemoveUser: AsyncUserAction;
  onResetPassword: AsyncUserAction;
  onCreateUser: AsyncAction;
  onEditingChange: Dispatch<SetStateAction<UserEditDraft>>;
  onCreateFormChange: Dispatch<SetStateAction<UserCreateForm>>;
};

function SettingsUsersHeader({
  lang,
  users,
  groups,
  onCreateUserClick,
}: {
  lang: "en" | "ru";
  users: AccessUser[];
  groups: AccessGroupOption[];
  onCreateUserClick: () => void;
}) {
  const copy = ACCESS_UI_TEXT[lang].users;
  const common = ACCESS_UI_TEXT[lang].common;
  const activeUsers = users.filter((user) => user.is_active).length;
  const staffUsers = users.filter((user) => user.is_staff).length;

  return (
    <>
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-3">
          <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-primary/10">
            <UsersIcon className="h-4 w-4 text-primary" />
          </div>
          <div>
            <h1 className="text-base font-semibold tracking-tight text-foreground">{copy.title}</h1>
            <p className="text-xs text-muted-foreground">{copy.subtitle}</p>
          </div>
        </div>
        <Button className="h-10 gap-2" onClick={onCreateUserClick}>
          <UserPlus className="h-4 w-4" />
          {copy.createAction}
        </Button>
      </div>

      <div className="flex flex-wrap items-center gap-5 rounded-xl border border-border/60 bg-secondary/10 px-5 py-3 shadow-sm">
        <div className="flex items-center gap-2">
          <UsersIcon className="h-4 w-4 text-muted-foreground/50" />
          <span className="text-sm font-medium text-foreground">{users.length}</span>
          <span className="text-xs text-muted-foreground">{lang === "ru" ? "всего" : "total"}</span>
        </div>
        <div className="h-4 w-px bg-border/60" />
        <div className="flex items-center gap-1.5">
          <div className="h-2 w-2 rounded-full bg-emerald-400/80" />
          <span className="text-sm font-medium text-foreground">{activeUsers}</span>
          <span className="text-xs text-muted-foreground">{common.active.toLowerCase()}</span>
        </div>
        <div className="h-4 w-px bg-border/60" />
        <div className="flex items-center gap-1.5">
          <div className="h-2 w-2 rounded-full bg-blue-400/80" />
          <span className="text-sm font-medium text-foreground">{staffUsers}</span>
          <span className="text-xs text-muted-foreground">{common.staff}</span>
        </div>
        <div className="h-4 w-px bg-border/60" />
        <div className="flex items-center gap-1.5">
          <div className="h-2 w-2 rounded-full bg-violet-400/80" />
          <span className="text-sm font-medium text-foreground">{groups.length}</span>
          <span className="text-xs text-muted-foreground">{common.groups.toLowerCase()}</span>
        </div>
      </div>
    </>
  );
}

export function SettingsUsersLayout({
  lang,
  users,
  groups,
  features,
  saving,
  editingId,
  editing,
  createForm,
  createValidation,
  editValidation,
  onStartEdit,
  onCancelEdit,
  onSaveEdit,
  onRemoveUser,
  onResetPassword,
  onCreateUser,
  onEditingChange,
  onCreateFormChange,
}: SettingsUsersLayoutProps) {
  const [createOpen, setCreateOpen] = useState(false);
  const copy = ACCESS_UI_TEXT[lang].users;

  return (
    <div className="space-y-6 pb-10">
      <SettingsUsersHeader lang={lang} users={users} groups={groups} onCreateUserClick={() => setCreateOpen(true)} />
      <UserDirectory
        lang={lang}
        users={users}
        groups={groups}
        features={features}
        saving={saving}
        editingId={editingId}
        editing={editing}
        editValidation={editValidation}
        onStartEdit={onStartEdit}
        onCancelEdit={onCancelEdit}
        onSaveEdit={onSaveEdit}
        onRemoveUser={onRemoveUser}
        onResetPassword={onResetPassword}
        onEditingChange={onEditingChange}
      />
      <Sheet open={createOpen} onOpenChange={setCreateOpen}>
        <SheetContent className="w-full overflow-y-auto p-0 sm:max-w-xl">
          <SheetHeader className="border-b border-border/70 px-6 py-5 pr-14">
            <SheetTitle className="flex items-center gap-2 text-base">
              <UserPlus className="h-4 w-4 text-primary" />
              {copy.createTitle}
            </SheetTitle>
            <SheetDescription>{copy.createHint}</SheetDescription>
          </SheetHeader>
          <CreateUserSidebar
            lang={lang}
            groups={groups}
            createForm={createForm}
            validation={createValidation}
            saving={saving}
            onCreateUser={async () => {
              const ok = await onCreateUser();
              if (ok) setCreateOpen(false);
              return ok;
            }}
            onCreateFormChange={onCreateFormChange}
          />
        </SheetContent>
      </Sheet>
    </div>
  );
}
