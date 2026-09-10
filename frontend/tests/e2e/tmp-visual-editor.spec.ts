import { expect, test } from "@playwright/test";
import { login } from "./helpers";

const pipelineBase = "/api/studio/pipelines/";
const shots = "C:/Users/nolos/AppData/Local/Temp/webterm-editor-shots";

test.use({ channel: "chrome" });

test("visual check of pipeline editor", async ({ page }) => {
  test.setTimeout(120_000);
  await login(page);
  const csrf = await page.request.get("/api/auth/csrf/");
  const headers = {
    "X-CSRFToken": (await csrf.json()).csrfToken as string,
    Origin: "http://127.0.0.1:8091",
  };
  const name = `qa_auto_visual_${Date.now()}`;
  const created = await page.request.post(pipelineBase, {
    headers,
    data: { name, description: "" },
  });
  expect(created.ok(), await created.text()).toBeTruthy();
  const id = (await created.json()).id as number;
  try {
    await page.goto(`/automation/pipelines/${id}`);
    await expect(page.locator(".react-flow__node")).toHaveCount(1);
    await page.waitForTimeout(600);
    await page.screenshot({ path: `${shots}/01-empty.png` });

    await page.getByRole("button", { name: "Добавить первый шаг" }).click();
    await page.waitForTimeout(300);
    await page.screenshot({ path: `${shots}/02-picker.png` });

    await page.getByLabel("Поиск шагов").fill("ssh");
    await page.keyboard.press("Enter");
    await page.waitForTimeout(300);
    await page.getByLabel("Название шага").fill("Проверить диск");
    await page.getByLabel("Команда *").fill("df -h / | tail -1");
    await page.waitForTimeout(300);
    await page.screenshot({ path: `${shots}/03-step-settings.png` });

    await page.getByRole("button", { name: "Следующий шаг" }).click();
    await page.getByLabel("Поиск шагов").fill("услов");
    await page.keyboard.press("Enter");
    await page.waitForTimeout(300);
    await page.getByRole("button", { name: "Следующий шаг" }).click();
    await page.getByLabel("Поиск шагов").fill("telegram");
    await page.waitForTimeout(200);
    await page
      .locator(".auto-node-picker")
      .getByRole("button", { name: /^Telegram/ })
      .click();
    await page.waitForTimeout(300);
    await page.keyboard.press("Escape");
    await page.getByRole("button", { name: "Вписать в экран" }).click();
    await page.waitForTimeout(500);
    await page.screenshot({ path: `${shots}/04-flow.png` });

    await page.getByRole("button", { name: "Включить тёмную тему" }).click();
    await page.waitForTimeout(400);
    await page.screenshot({ path: `${shots}/05-flow-dark.png` });
    await page.locator(".react-flow__node .auto-step-title").nth(1).click();
    await page.waitForTimeout(600);
    console.log(
      "settings after title click:",
      await page.locator(".auto-node-settings").count(),
      "selected nodes:",
      await page.locator(".react-flow__node.selected").count(),
    );
    const box = await page.locator(".react-flow__node").nth(2).boundingBox();
    await page.mouse.click(box!.x + 60, box!.y + 20);
    await page.waitForTimeout(600);
    console.log(
      "settings after mouse click:",
      await page.locator(".auto-node-settings").count(),
    );
    await page.locator(".react-flow__node").nth(3).dispatchEvent("click");
    await page.waitForTimeout(400);
    console.log(
      "settings after dispatch click:",
      await page.locator(".auto-node-settings").count(),
    );
    await page.screenshot({ path: `${shots}/06-dark-settings.png` });
  } finally {
    await page.request.delete(`${pipelineBase}${id}/`, { headers });
  }
});
