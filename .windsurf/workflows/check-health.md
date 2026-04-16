---
description: Full health check of the WEU AI Platform project (architecture, tests, quality)
---

# Полная проверка здоровья проекта

// turbo
## Шаг 1. Django system check

```bash
python manage.py check
```

Ожидается: `System check identified no issues (0 silenced)`

// turbo
## Шаг 2. Ruff linting

```bash
ruff check .
```

Ожидается: 0 ошибок

// turbo
## Шаг 3. Cross-context imports check

```bash
python -c "
import os, sys, pathlib
sys.path.insert(0,'.')
os.environ['DJANGO_SETTINGS_MODULE']='web_ui.settings.development'
import django; django.setup()

ALLOWED_MODS = {
    'servers.mcp_tool_runtime', 'core_ui.desktop_api.views',
    'core_ui.desktop_api.serializers', 'core_ui.views._views_all',
    'core_ui.management.commands.seed_multi_user_smoke',
    'app.tools.server_tools', 'app.tools.ssh_tools',
}
checks = [('servers','studio'),('core_ui','servers'),('core_ui','studio'),('app.core','servers'),('app.tools','servers')]
violations = []
for src_pkg, dst_pkg in checks:
    for py in pathlib.Path(src_pkg.replace('.','/')).rglob('*.py'):
        mod = py.with_suffix('').as_posix().replace('/','.')
        if mod in ALLOWED_MODS: continue
        for lineno, line in enumerate(py.read_text(encoding='utf-8',errors='ignore').splitlines(), 1):
            s = line.strip()
            if (f'from {dst_pkg}' in s or f'import {dst_pkg}' in s) and not s.startswith('#'):
                violations.append(f'{mod}:{lineno}: {s[:80]}')
print('VIOLATIONS:' if violations else 'CROSS-CONTEXT: GREEN')
for v in violations: print(' ', v)
"
```

Ожидается: `CROSS-CONTEXT: GREEN`

// turbo
## Шаг 4. Миграции

```bash
python manage.py migrate --check
```

Ожидается: нет непримененных миграций

// turbo
## Шаг 5. Тесты

```bash
pytest --tb=short -q
```

// turbo
## Шаг 6. Frontend TypeScript check

```bash
cd ai-server-terminal-main && npm run type-check
```

## Шаг 7. Итог

Проект здоров если все шаги прошли без ошибок.
