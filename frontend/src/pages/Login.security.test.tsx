import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import Login from "@/pages/Login";
import { I18nProvider } from "@/lib/i18n";

const mocks = vi.hoisted(() => ({
  authLogin: vi.fn(),
  fetchAuthSession: vi.fn(),
  navigate: vi.fn(),
  searchParams: new URLSearchParams(),
}));

vi.mock("react-router-dom", async (importOriginal) => {
  const actual = await importOriginal<typeof import("react-router-dom")>();
  return {
    ...actual,
    useNavigate: () => mocks.navigate,
    useSearchParams: () => [mocks.searchParams, vi.fn()],
  };
});

vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api")>();
  return {
    ...actual,
    authLogin: mocks.authLogin,
    fetchAuthSession: mocks.fetchAuthSession,
  };
});

function renderLogin(next = "") {
  mocks.searchParams = new URLSearchParams(next ? { next } : undefined);
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <I18nProvider>
        <Login />
      </I18nProvider>
    </QueryClientProvider>,
  );
}

async function submitLocalLogin(container: HTMLElement) {
  const username = container.querySelector<HTMLInputElement>("#username");
  const password = container.querySelector<HTMLInputElement>("#password");
  const form = username?.closest("form");
  expect(username).not.toBeNull();
  expect(password).not.toBeNull();
  expect(form).not.toBeNull();
  fireEvent.change(username!, { target: { value: "admin" } });
  fireEvent.change(password!, { target: { value: "password" } });
  fireEvent.submit(form!);
  await waitFor(() => expect(mocks.authLogin).toHaveBeenCalledOnce());
}

describe("Login post-auth redirect security", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.authLogin.mockResolvedValue({
      success: true,
      authenticated: true,
      next_url: "/servers",
      user: { id: 1, username: "admin", email: "admin@example.test", is_staff: true, features: {} },
    });
  });

  it.each([
    "https://evil.example/phish",
    "//evil.example/phish",
    "/\\evil.example/phish",
    "javascript:alert(1)",
    "data:text/html,phish",
    "\n//evil.example/phish",
  ])("rejects an unsafe next query target: %s", async (next) => {
    const { container } = renderLogin(next);

    await submitLocalLogin(container);

    await waitFor(() => expect(mocks.navigate).toHaveBeenCalledWith("/dashboard", { replace: true }));
  });

  it("rejects an unsafe backend next_url when the query has no target", async () => {
    mocks.authLogin.mockResolvedValueOnce({
      success: true,
      authenticated: true,
      next_url: "https://evil.example/from-backend",
      user: { id: 1, username: "admin", email: "admin@example.test", is_staff: true, features: {} },
    });
    const { container } = renderLogin();

    await submitLocalLogin(container);

    await waitFor(() => expect(mocks.navigate).toHaveBeenCalledWith("/dashboard", { replace: true }));
  });

  it("keeps a safe internal next query target", async () => {
    const { container } = renderLogin("/servers?group=prod#active");

    await submitLocalLogin(container);

    await waitFor(() =>
      expect(mocks.navigate).toHaveBeenCalledWith("/servers?group=prod#active", { replace: true }),
    );
  });

  it("keeps a safe backend next_url when the query has no target", async () => {
    const { container } = renderLogin();

    await submitLocalLogin(container);

    await waitFor(() => expect(mocks.navigate).toHaveBeenCalledWith("/servers", { replace: true }));
  });
});
