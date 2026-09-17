export type PermissionMode = "inherit" | "allow" | "deny";

export type AccessFeatureOption = {
  value: string;
  label: string;
};

export type AccessGroupOption = {
  id: number;
  name: string;
};

export type UserCreateForm = {
  username: string;
  email: string;
  password: string;
  is_staff: boolean;
  is_active: boolean;
  access_profile: string;
  groups: number[];
};

export type UserEditDraft = {
  username?: string;
  email?: string;
  is_staff?: boolean;
  is_active?: boolean;
  access_profile?: string;
  groups?: number[];
  permission_modes?: Record<string, PermissionMode>;
};
