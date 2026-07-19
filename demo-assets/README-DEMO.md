# WebTerm — запись демо с реальной платформы

Это **не AI-генерация**. Видео снято Playwright’ом из **реального React UI** (`frontend/`) с API-фикстурами (как в e2e): те же компоненты, layout, кнопки, что в продукте.

## Файл

- `webterm-product-demo-tour.webm` (~47 c) — тур:
  Панель → Серверы (список + «Добавить сервер») → «Расширенные»:
  **Доступ/шаринг** (активные доступы + выдача нового) → **Знания** (ручные заметки + AI-память)
  → Терминал (SSH) → Файлы (SFTP) → AI-ассистент (Nova) → Агенты → Студия → Настройки → Серверы.

## Перезаписать (когда UI обновится)

```powershell
cd frontend
npm run demo:record
```

Видео появится в:

`frontend/demo-recordings/product-demo-tour-.../video.webm`

Скопировать:

```powershell
Copy-Item frontend\demo-recordings\**\video.webm demo-assets\webterm-product-demo-tour.webm -Force
```

## Headed (смотреть глазами во время записи)

```powershell
cd frontend
npx playwright test --config=playwright.demo.config.ts --project=chromium-demo --headed --slow-mo=400
```

## Скрипт тура (e2e)

`frontend/e2e/product-demo-tour.spec.ts`  
Конфиг: `frontend/playwright.demo.config.ts`

## Ограничения

- API **замокан** фикстурами (как visual e2e): UI настоящий, данные демо.
- Для записи **живого** backend (реальные сервера/SSH): поднять `npm run dev` + backend и править tour под `baseURL` / без mocks.
- WebM → MP4 (если нужен): `ffmpeg -i webterm-product-demo-tour.webm -c:v libx264 -pix_fmt yuv420p webterm-product-demo-tour.mp4`

## Текст для озвучки (~45–60 с)

1. **Панель** — единый ops workspace.  
2. **Серверы** — inventory, группы, онлайн, «Добавить сервер».  
3. **Шаринг** — выдать коллеге доступ к серверу, активные доступы и роли.  
4. **Заметки** — ручные знания по серверу (nginx, ротация секретов).  
5. **Память** — AI сам накапливает профиль, доступы, риски и runbook’и.  
6. **Терминал** — browser SSH + Linux workspace.  
7. **Файлы** — SFTP рядом с сессией.  
8. **Ассистент** — AI (Nova) в контексте сервера и его вывода.  
9. **Агенты** — full agent, сценарии, запуск.  
10. **Студия / Настройки** — автоматизация и readiness.

## Демо-данные

Вкладки «Доступ» и «Знания» наполнены фикстурами только для этого тура — флаг
`demoData: true` в `installPlatformMocks` (`frontend/e2e/support/platformFixtureServerDetail.ts`).
Обычные e2e/visual тесты по-прежнему видят пустые вкладки.
