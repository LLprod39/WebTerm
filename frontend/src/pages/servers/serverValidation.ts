import { z } from "zod";

import type { ServerForm } from "./types";

type Translate = (key: string) => string;

export type ServerFormField =
  | "name"
  | "host"
  | "port"
  | "username"
  | "ssh_private_key"
  | "password"
  | "sudo_password";

export type ServerFormErrors = Partial<Record<ServerFormField, string>>;

export type ServerValidationResult = {
  errors: ServerFormErrors;
  isValid: boolean;
  summary: string;
};

function schema(t: Translate, hasSavedSudoPassword: boolean) {
  return z
    .object({
      name: z.string().trim().min(1, t("srv.validation_name_required")),
      host: z.string().trim().min(1, t("srv.validation_host_required")),
      port: z.coerce.number().int().min(1, t("srv.validation_port_invalid")).max(65535, t("srv.validation_port_invalid")),
      username: z.string().trim().min(1, t("srv.validation_username_required")),
      auth_method: z.enum(["password", "key", "key_password"]),
      key_path: z.string(),
      ssh_private_key: z.string(),
      sudo_auth_mode: z.enum(["none", "nopasswd", "stored_password"]),
      sudo_password: z.string(),
    })
    .superRefine((value, ctx) => {
      if (value.auth_method !== "password" && !value.key_path && !value.ssh_private_key.trim()) {
        ctx.addIssue({ code: z.ZodIssueCode.custom, path: ["ssh_private_key"], message: t("srv.validation_key_required") });
      }
      if (value.sudo_auth_mode === "stored_password" && !value.sudo_password.trim() && !hasSavedSudoPassword) {
        ctx.addIssue({ code: z.ZodIssueCode.custom, path: ["sudo_password"], message: t("srv.validation_sudo_password_required") });
      }
    });
}

export function validateServerForm(
  form: ServerForm,
  t: Translate,
  hasSavedSudoPassword = false,
): ServerValidationResult {
  const result = schema(t, hasSavedSudoPassword).safeParse(form);
  if (result.success) {
    return { errors: {}, isValid: true, summary: "" };
  }

  const errors: ServerFormErrors = {};
  for (const issue of result.error.issues) {
    const field = issue.path[0] as ServerFormField | undefined;
    if (field && !errors[field]) errors[field] = issue.message;
  }

  return {
    errors,
    isValid: false,
    summary: Object.values(errors)[0] || t("srv.form_incomplete"),
  };
}
