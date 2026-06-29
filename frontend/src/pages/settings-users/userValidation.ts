import { z } from "zod";

import { ACCESS_PROFILE_OPTIONS } from "@/lib/accessUiText";
import type { UserCreateForm, UserEditDraft } from "./settingsUsersTypes";

type Lang = "en" | "ru";

export type UserFormField = "username" | "email" | "password" | "access_profile";

export type UserFormErrors = Partial<Record<UserFormField, string>>;

export type UserValidationResult = {
  errors: UserFormErrors;
  isValid: boolean;
  summary: string;
};

const accessProfiles = ACCESS_PROFILE_OPTIONS;

const userNamePattern = /^[A-Za-z0-9_.@+-]+$/;

function text(lang: Lang) {
  return lang === "ru"
    ? {
        usernameRequired: "Укажите логин.",
        usernameFormat: "Логин может содержать латиницу, цифры и символы . _ @ + -.",
        emailFormat: "Введите корректный email или оставьте поле пустым.",
        passwordRequired: "Укажите пароль.",
        passwordLength: "Пароль должен быть не короче 12 символов.",
        passwordComplexity: "Пароль должен содержать минимум три типа символов.",
        passwordUsername: "Пароль не должен содержать логин.",
        profile: "Выберите профиль доступа.",
        summary: "Исправьте поля формы перед сохранением.",
      }
    : {
        usernameRequired: "Enter a username.",
        usernameFormat: "Username may include letters, numbers, and . _ @ + -.",
        emailFormat: "Enter a valid email or leave it blank.",
        passwordRequired: "Enter a password.",
        passwordLength: "Password must be at least 12 characters.",
        passwordComplexity: "Password must use at least three character classes.",
        passwordUsername: "Password must not contain the username.",
        profile: "Choose an access profile.",
        summary: "Fix the form fields before saving.",
      };
}

function complexityScore(value: string) {
  return [
    /[a-z]/.test(value),
    /[A-Z]/.test(value),
    /\d/.test(value),
    /[^A-Za-z0-9]/.test(value),
  ].filter(Boolean).length;
}

function baseUserSchema(lang: Lang) {
  const copy = text(lang);
  return z.object({
    username: z
      .string()
      .trim()
      .min(1, copy.usernameRequired)
      .min(3, copy.usernameRequired)
      .max(150, copy.usernameFormat)
      .regex(userNamePattern, copy.usernameFormat),
    email: z.string().trim().refine((value) => !value || z.string().email().safeParse(value).success, copy.emailFormat),
    access_profile: z.enum(accessProfiles, { errorMap: () => ({ message: copy.profile }) }),
  });
}

function passwordSchema(username: string | undefined, lang: Lang) {
  const copy = text(lang);
  return z
    .string()
    .min(1, copy.passwordRequired)
    .min(12, copy.passwordLength)
    .refine((value) => complexityScore(value) >= 3, copy.passwordComplexity)
    .refine((value) => {
      const normalizedUser = username?.trim().toLowerCase();
      return !normalizedUser || !value.toLowerCase().includes(normalizedUser);
    }, copy.passwordUsername);
}

function toResult(result: z.SafeParseReturnType<unknown, unknown>, lang: Lang): UserValidationResult {
  if (result.success) {
    return { errors: {}, isValid: true, summary: "" };
  }

  const errors: UserFormErrors = {};
  for (const issue of result.error.issues) {
    const field = issue.path[0] as UserFormField | undefined;
    if (field && !errors[field]) {
      errors[field] = issue.message;
    }
  }

  return {
    errors,
    isValid: false,
    summary: Object.values(errors)[0] || text(lang).summary,
  };
}

export function validateCreateUserForm(form: UserCreateForm, lang: Lang): UserValidationResult {
  const schema = baseUserSchema(lang).extend({
    password: passwordSchema(form.username, lang),
  });

  return toResult(schema.safeParse(form), lang);
}

export function validateEditUserDraft(draft: UserEditDraft, lang: Lang): UserValidationResult {
  const schema = baseUserSchema(lang);
  return toResult(
    schema.safeParse({
      username: draft.username ?? "",
      email: draft.email ?? "",
      access_profile: draft.access_profile ?? "custom",
    }),
    lang,
  );
}
