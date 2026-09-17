import { Page, Route } from "@playwright/test";

export interface ApiRequest {
  method: string;
  path: string;
  query: Record<string, string>;
  body: unknown;
  url: URL;
}

export interface ApiResponse {
  status?: number;
  body?: unknown;
}

export interface ApiHarness {
  calls: ApiRequest[];
  clearCalls: () => void;
  getCalls: (path: string, method?: string) => ApiRequest[];
}

export type ApiHandler = (req: ApiRequest, route: Route) => Promise<ApiResponse | void> | ApiResponse | void;

function parseBody(raw: string | null): unknown {
  if (!raw) return null;
  try {
    return JSON.parse(raw);
  } catch {
    return raw;
  }
}

function isApiPath(pathname: string): boolean {
  return pathname.startsWith("/api/") || pathname.startsWith("/servers/api/");
}

export async function installApiHarness(page: Page, handler: ApiHandler, lang: "en" | "ru" = "en"): Promise<ApiHarness> {
  const calls: ApiRequest[] = [];

  await page.addInitScript((initialLang) => {
    window.localStorage.setItem("weu_lang", initialLang);
  }, lang);

  await page.route("**/*", async (route) => {
    const request = route.request();
    const url = new URL(request.url());

    if (!isApiPath(url.pathname)) {
      await route.continue();
      return;
    }

    const apiRequest: ApiRequest = {
      method: request.method().toUpperCase(),
      path: url.pathname,
      query: Object.fromEntries(url.searchParams.entries()),
      body: parseBody(request.postData()),
      url,
    };

    calls.push(apiRequest);

    const response = await handler(apiRequest, route);
    if (response) {
      await route.fulfill({
        status: response.status ?? 200,
        contentType: "application/json",
        body: JSON.stringify(response.body ?? {}),
      });
      return;
    }

    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: "{}",
    });
  });

  return {
    calls,
    clearCalls: () => {
      calls.splice(0, calls.length);
    },
    getCalls: (path: string, method?: string) => {
      const wanted = method?.toUpperCase();
      return calls.filter((call) => call.path === path && (!wanted || call.method === wanted));
    },
  };
}

export function json(body: unknown, status = 200): ApiResponse {
  return { status, body };
}
