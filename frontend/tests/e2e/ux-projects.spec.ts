import { test, expect, type Page } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { login, credentials, assertNoOverflow } from "./helpers";

async function headers(page: Page) {
  const result = await page.request.get("/api/auth/csrf/");
  return {
    "X-CSRFToken": (await result.json()).csrfToken,
    Origin: "http://127.0.0.1:8091",
  };
}
async function loginAs(page: Page, username: string) {
  const result = await page.request.post("/api/auth/login/", {
    headers: await headers(page),
    data: { username, password: credentials.password, auth_mode: "local" },
  });
  expect(result.ok()).toBeTruthy();
}
async function projectData(page: Page) {
  const result = await page.request.get("/api/projects/");
  expect(result.ok()).toBeTruthy();
  return result.json() as Promise<{
    projects: { id: string; name: string; is_default: boolean }[];
    active_project_id: string;
  }>;
}
async function openProjects(page: Page) {
  await page
    .getByRole("button", { name: "Выбрать рабочий проект", exact: true })
    .click();
  await expect(page.getByRole("dialog")).toBeVisible();
}

test("projects UX: real creation, switching, membership roles, duplicate prevention and removal", async ({
  page,
  browser,
  baseURL,
}) => {
  test.setTimeout(120_000);
  expect(baseURL).toBe("http://127.0.0.1:8091");
  await login(page);
  const names = [
    `qa_ux_projects_owner_${Date.now()}`,
    `qa_ux_projects_member_${Date.now()}`,
  ];
  const createdUsers: number[] = [];
  const ownerContext = await browser.newContext({ baseURL });
  const memberContext = await browser.newContext({ baseURL });
  try {
    for (const username of names) {
      const result = await page.request.post("/api/access/users/", {
        headers: await headers(page),
        data: {
          username,
          password: credentials.password,
          access_profile: "custom",
          explicit_permissions: { servers: true },
          is_active: true,
        },
      });
      expect(result.ok()).toBeTruthy();
      const users = (
        await (await page.request.get("/api/access/users/")).json()
      ).users as { id: number; username: string }[];
      createdUsers.push(users.find((user) => user.username === username)!.id);
    }
    const owner = await ownerContext.newPage();
    const member = await memberContext.newPage();
    await loginAs(owner, names[0]);
    await loginAs(member, names[1]);
    await owner.goto("/");
    const initial = await projectData(owner);
    const projectName = `QA UX Team ${Date.now()}`;
    await openProjects(owner);
    await owner
      .getByRole("button", { name: "Создать проект", exact: true })
      .click();
    await expect(
      owner.getByRole("button", { name: "Создать и переключить", exact: true }),
    ).toBeDisabled();
    const name = owner.getByRole("textbox", {
      name: "Название проекта",
      exact: true,
    });
    await expect(name).toHaveAttribute("maxlength", "120");
    await name.fill(projectName);
    await owner.setViewportSize({ width: 390, height: 844 });
    await expect(name).toHaveValue(projectName);
    await assertNoOverflow(owner);
    await owner.setViewportSize({ width: 1440, height: 960 });
    await expect(name).toHaveValue(projectName);
    await owner
      .getByRole("button", { name: "Создать и переключить", exact: true })
      .click();
    await expect(owner.getByRole("dialog")).toHaveCount(0);
    const afterCreate = await projectData(owner);
    const project = afterCreate.projects.find(
      (value) => value.name === projectName,
    )!;
    expect(afterCreate.active_project_id).toBe(project.id);
    await openProjects(owner);
    await expect(
      owner.getByRole("textbox", { name: "Название проекта", exact: true }),
    ).toHaveCount(0);
    const search = owner.getByRole("textbox", {
      name: "Найти проект…",
      exact: true,
    });
    await search.fill("missing-project-qa");
    await expect(
      owner.getByText("Проекты не найдены", { exact: true }),
    ).toBeVisible();
    await search.fill(projectName);
    await owner.getByRole("button", { name: "Участники", exact: true }).click();
    const identity = owner.getByRole("textbox", {
      name: "Добавить существующего пользователя",
      exact: true,
    });
    await identity.fill(names[1]);
    await owner.getByRole("button", { name: "Добавить", exact: true }).click();
    const role = owner.getByRole("combobox", {
      name: `Роль ${names[1]}`,
      exact: true,
    });
    await expect(role).toHaveValue("viewer");
    await identity.fill(names[1]);
    await expect(
      owner.getByRole("button", { name: "Добавить", exact: true }),
    ).toBeDisabled();
    await expect(owner.getByText(/уже.*проект/i)).toBeVisible();
    await identity.fill("");
    await role.selectOption("operator");
    await expect(owner.getByRole("dialog").last()).toContainText("Оператор");
    await owner
      .getByRole("dialog")
      .last()
      .getByRole("button", { name: "Отмена", exact: true })
      .click();
    await expect(role).toHaveValue("viewer");
    await role.selectOption("admin");
    await owner
      .getByRole("dialog")
      .last()
      .getByRole("button", { name: "Изменить роль", exact: true })
      .click();
    await expect(role).toHaveValue("admin");
    // An administrator can downgrade their own membership; the controls must
    // reflect the refreshed project permissions without closing the drawer.
    await member.goto("/");
    await openProjects(member);
    await member
      .getByRole("textbox", { name: "Найти проект…", exact: true })
      .fill(projectName);
    await member
      .getByRole("button", { name: "Участники", exact: true })
      .click();
    await member
      .getByRole("combobox", { name: `Роль ${names[1]}`, exact: true })
      .selectOption("viewer");
    await member
      .getByRole("dialog")
      .last()
      .getByRole("button", { name: "Изменить роль", exact: true })
      .click();
    await expect(
      member.getByRole("combobox", { name: `Роль ${names[1]}`, exact: true }),
    ).toHaveCount(0);
    await expect(
      member.getByRole("textbox", {
        name: "Добавить существующего пользователя",
        exact: true,
      }),
    ).toHaveCount(0);
    const forbidden = await member.request.patch(
      `/api/projects/${project.id}/members/${createdUsers[0]}/`,
      { headers: await headers(member), data: { role: "admin" } },
    );
    expect(forbidden.status()).toBe(403);
    await owner
      .getByRole("textbox", { name: "Найти участника…", exact: true })
      .fill("missing-member-qa");
    await expect(
      owner.getByRole("heading", { name: "Ничего не найдено", exact: true }),
    ).toBeVisible();
    await owner
      .getByRole("button", { name: "Очистить поиск", exact: true })
      .click();
    await owner
      .getByRole("button", {
        name: `Убрать ${names[1]} из проекта`,
        exact: true,
      })
      .click();
    await owner
      .getByRole("dialog")
      .last()
      .getByRole("button", { name: "Отмена", exact: true })
      .click();
    await expect(role).toBeVisible();
    await owner
      .getByRole("button", {
        name: `Убрать ${names[1]} из проекта`,
        exact: true,
      })
      .click();
    await owner
      .getByRole("button", { name: "Убрать участника", exact: true })
      .click();
    await expect(role).toHaveCount(0);
    const a11y = await new AxeBuilder({ page: owner })
      .withTags(["wcag2a", "wcag2aa", "wcag21aa"])
      .analyze();
    expect(a11y.violations).toEqual([]);
    await owner
      .getByRole("button", { name: "К проектам", exact: true })
      .click();
    await search.fill(
      initial.projects.find((value) => value.id === initial.active_project_id)!
        .name,
    );
    await owner
      .getByRole("button", { name: "Переключить", exact: true })
      .click();
    await expect(owner.getByRole("dialog")).toHaveCount(0);
    expect((await projectData(owner)).active_project_id).toBe(
      initial.active_project_id,
    );
  } finally {
    await ownerContext.close();
    await memberContext.close();
    // These exact disposable users own all projects created by this test.
    // Account deletion cascades their empty QA projects and memberships.
    for (const id of createdUsers) {
      const removed = await page.request.delete(`/api/access/users/${id}/`, {
        headers: await headers(page),
      });
      expect(removed.ok()).toBeTruthy();
    }
  }
});

test("projects UX fixtures: list outage, retry, empty state and retained creation draft", async ({
  page,
}) => {
  await login(page);
  let failed = true;
  await page.route("**/api/projects/", async (route) => {
    if (route.request().method() !== "GET") return route.continue();
    await route.fulfill({
      status: failed ? 503 : 200,
      contentType: "application/json",
      body: JSON.stringify(
        failed
          ? { error: "Проекты временно недоступны" }
          : { projects: [], active_project_id: null },
      ),
    });
  });
  await page.goto("/");
  await openProjects(page);
  await expect(page.getByRole("alert")).toContainText(
    "Проекты временно недоступны",
  );
  failed = false;
  await page
    .getByRole("dialog")
    .getByRole("button", { name: "Повторить", exact: true })
    .click();
  await expect(page.getByRole("alert")).toHaveCount(0);
  await expect(
    page.getByRole("button", { name: "Создать проект", exact: true }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Создать проект", exact: true })
    .click();
  await page
    .getByRole("textbox", { name: "Название проекта", exact: true })
    .fill("Unsaved QA draft");
  await page.getByRole("button", { name: "Закрыть", exact: true }).click();
  await openProjects(page);
  await page
    .getByRole("button", { name: "Создать проект", exact: true })
    .click();
  await expect(
    page.getByRole("textbox", { name: "Название проекта", exact: true }),
  ).toHaveValue("Unsaved QA draft");
  await page.getByRole("button", { name: "Отмена", exact: true }).click();
  await page
    .getByRole("button", { name: "Создать проект", exact: true })
    .click();
  await expect(
    page.getByRole("textbox", { name: "Название проекта", exact: true }),
  ).toHaveValue("");
});

test("projects UX fixtures: member loading error, pagination, sorting and pending add recovery", async ({
  page,
}) => {
  await login(page);
  const projects = await projectData(page);
  const active = projects.projects.find(
    (project) => project.id === projects.active_project_id,
  )!;
  let failed = true;
  const members = Array.from({ length: 18 }, (_, index) => ({
    user_id: 9000 + index,
    username: `qa_fixture_member_${String(index).padStart(2, "0")}`,
    email: `fixture${index}@example.test`,
    role: index === 0 ? "owner" : "viewer",
    is_active: true,
    joined_at: new Date(Date.UTC(2026, 8, 1, index)).toISOString(),
  }));
  await page.route(`**/api/projects/${active.id}/members/`, async (route) => {
    if (route.request().method() !== "GET") return route.continue();
    await route.fulfill({
      status: failed ? 503 : 200,
      contentType: "application/json",
      body: JSON.stringify(
        failed ? { error: "Участники временно недоступны" } : { members },
      ),
    });
  });
  await page.goto("/");
  await openProjects(page);
  await page
    .getByRole("textbox", { name: "Найти проект…", exact: true })
    .fill(active.name);
  await page.getByRole("button", { name: "Участники", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText(
    "Участники временно недоступны",
  );
  failed = false;
  await page
    .getByRole("dialog")
    .getByRole("button", { name: "Повторить", exact: true })
    .click();
  await expect(page.getByRole("table").getByRole("row")).toHaveCount(16);
  await page
    .getByRole("button", { name: "Следующая страница", exact: true })
    .click();
  await expect(page.getByRole("table").getByRole("row")).toHaveCount(4);
  await page
    .getByRole("button", { name: "Предыдущая страница", exact: true })
    .click();
  for (const title of ["Участник", "Добавлен"]) {
    const header = page.getByRole("columnheader", { name: title, exact: true });
    await header.getByRole("button", { name: title, exact: true }).click();
    await expect(header).toHaveAttribute("aria-sort", "ascending");
  }
  let release: () => void = () => {};
  const pending = new Promise<void>((resolve) => {
    release = resolve;
  });
  await page.route(`**/api/projects/${active.id}/members/`, async (route) => {
    if (route.request().method() !== "POST") return route.fallback();
    await pending;
    await route.fulfill({
      status: 503,
      contentType: "application/json",
      body: JSON.stringify({ error: "Добавление временно недоступно" }),
    });
  });
  const identity = page.getByRole("textbox", {
    name: "Добавить существующего пользователя",
    exact: true,
  });
  await identity.fill("qa_fixture_new_member");
  await page.getByRole("button", { name: "Добавить", exact: true }).click();
  await expect(identity).toBeDisabled();
  await expect(
    page.getByRole("combobox", { name: "Роль", exact: true }),
  ).toBeDisabled();
  release();
  await expect(page.getByRole("alert")).toContainText(
    "Добавление временно недоступно",
  );
  await expect(identity).toHaveValue("qa_fixture_new_member");
  await expect(identity).toBeEnabled();
});
