export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
    public details?: unknown,
  ) {
    super(message);
    this.name = "ApiError";
  }
}
let csrfToken = "";
let csrfRequest: Promise<string> | null = null;
async function csrf() {
  if (csrfToken) return csrfToken;
  if (!csrfRequest)
    csrfRequest = fetch("/api/auth/csrf/", {
      credentials: "include",
      signal: AbortSignal.timeout(15_000),
      headers: { Accept: "application/json" },
    })
      .then(async (r) => {
        if (!r.ok)
          throw new ApiError(
            "Не удалось подготовить защищённое соединение",
            r.status,
          );
        const data = (await r.json()) as { csrfToken: string };
        if (!data.csrfToken)
          throw new ApiError(
            "Сервер не вернул токен защиты. Обновите страницу.",
            502,
          );
        csrfToken = data.csrfToken;
        return csrfToken;
      })
      .finally(() => {
        csrfRequest = null;
      });
  return csrfRequest;
}
export function clearCsrf() {
  csrfToken = "";
}
export async function request<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const method = (options.method || "GET").toUpperCase();
  const headers = new Headers(options.headers);
  headers.set("Accept", "application/json");
  if (options.body && !(options.body instanceof FormData))
    headers.set("Content-Type", "application/json");
  if (!["GET", "HEAD", "OPTIONS"].includes(method))
    headers.set("X-CSRFToken", await csrf());
  let response: Response;
  const timeout = AbortSignal.timeout(method === "GET" ? 45_000 : 180_000);
  const signal = options.signal
    ? AbortSignal.any([options.signal, timeout])
    : timeout;
  try {
    response = await fetch(path, {
      ...options,
      headers,
      signal,
      credentials: "include",
    });
  } catch (error) {
    if (timeout.aborted)
      throw new ApiError(
        method === "GET"
          ? "Сервер не ответил вовремя. Повторите запрос."
          : "Время ожидания истекло. Проверьте результат операции перед повторной отправкой.",
        408,
      );
    if (error instanceof Error && error.name === "AbortError") throw error;
    throw new ApiError(
      "Нет соединения с сервером. Проверьте сеть и повторите запрос.",
      0,
    );
  }
  const json = response.headers
    .get("content-type")
    ?.includes("application/json");
  const loginAttempt = path.split("?")[0] === "/api/auth/login/";
  if (
    (response.status === 401 && !loginAttempt) ||
    (response.redirected && !json)
  ) {
    window.dispatchEvent(new Event("webterm:session-expired"));
    throw new ApiError("Сессия завершена. Войдите снова.", 401);
  }
  if (response.status === 204) return undefined as T;
  if (!json)
    throw new ApiError(
      response.status === 403
        ? "Доступ запрещён. Обновите страницу и проверьте права."
        : "Сервис вернул неподдерживаемый ответ. Повторите запрос.",
      response.status,
    );
  const parsed: unknown = await response.json();
  if (parsed === null) {
    if (!response.ok)
      throw new ApiError("Не удалось выполнить запрос.", response.status);
    return null as T;
  }
  const data = parsed as Record<string, unknown>;
  if (!response.ok || data.success === false) {
    const message =
      loginAttempt && response.status === 401
        ? "Неверный логин или пароль. Проверьте данные и повторите вход."
        : typeof data.error === "string"
          ? data.error
          : typeof data.message === "string"
            ? data.message
            : typeof data.detail === "string"
              ? data.detail
              : response.status === 403
                ? "Недостаточно прав для этого действия."
                : "Не удалось выполнить запрос.";
    throw new ApiError(message, response.status, data);
  }
  // APIContractMiddleware envelopes bare lists while retaining legacy object fields.
  // Unwrap only its exact wrapper, never an entity that happens to have a data field.
  if (
    data &&
    !Array.isArray(data) &&
    data.success === true &&
    data.code === "ok" &&
    "data" in data &&
    Object.keys(data).every((key) => ["success", "code", "data"].includes(key))
  ) {
    return data.data as T;
  }
  return data as T;
}
export const api = {
  get: <T>(path: string, signal?: AbortSignal) => request<T>(path, { signal }),
  post: <T>(path: string, body: unknown = {}) =>
    request<T>(path, { method: "POST", body: JSON.stringify(body) }),
  put: <T>(path: string, body: unknown = {}) =>
    request<T>(path, { method: "PUT", body: JSON.stringify(body) }),
  patch: <T>(path: string, body: unknown = {}) =>
    request<T>(path, { method: "PATCH", body: JSON.stringify(body) }),
  delete: <T>(path: string, body?: unknown) =>
    request<T>(path, {
      method: "DELETE",
      body: body === undefined ? undefined : JSON.stringify(body),
    }),
  upload: <T>(path: string, body: FormData) =>
    request<T>(path, { method: "POST", body }),
};
export async function downloadFile(
  path: string,
  filename: string,
  body?: unknown,
) {
  const headers = new Headers();
  const method = body === undefined ? "GET" : "POST";
  if (body !== undefined) {
    headers.set("Content-Type", "application/json");
    headers.set("X-CSRFToken", await csrf());
  }
  const response = await fetch(path, {
    method,
    headers,
    credentials: "include",
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (
    response.status === 401 ||
    (response.redirected &&
      response.headers.get("content-type")?.includes("text/html"))
  ) {
    window.dispatchEvent(new Event("webterm:session-expired"));
    throw new ApiError("Сессия завершена", 401);
  }
  const attachment = /\battachment\b/i.test(
    response.headers.get("content-disposition") ?? "",
  );
  if (
    !response.ok ||
    (!attachment &&
      response.headers.get("content-type")?.includes("application/json"))
  ) {
    const data = (await response
      .json()
      .catch(() => ({ error: "Не удалось скачать файл" }))) as {
      error?: string;
    };
    throw new ApiError(
      data.error || "Не удалось скачать файл",
      response.status,
    );
  }
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
