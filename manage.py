#!/usr/bin/env python
"""Django's command-line utility for administrative tasks."""

import contextlib
import os
import sys
from pathlib import Path

# Загрузка .env до любых настроек Django (важно для WSL/Docker)
try:
    from dotenv import load_dotenv

    project_root = Path(__file__).resolve().parent
    load_dotenv(project_root / ".env")
except ImportError:
    pass


def main():
    """Run administrative tasks."""
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "web_ui.settings.development")
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Are you sure it's installed and "
            "available on your PYTHONPATH environment variable? Did you "
            "forget to activate a virtual environment?"
        ) from exc

    # Если запускается runserver без указания порта, используем порт из переменной окружения или 9000.
    # В WSL биндимся на 0.0.0.0, иначе Windows/Vite могут зависать на localhost relay.
    if len(sys.argv) >= 2 and sys.argv[1] == "runserver" and len(sys.argv) == 2:
        default_port = os.getenv("DJANGO_PORT", "9000")
        if ":" in default_port:
            sys.argv.append(default_port)
        else:
            runserver_host = os.getenv("DJANGO_RUNSERVER_HOST")
            if not runserver_host:
                proc_version = ""
                with contextlib.suppress(OSError):
                    proc_version = Path("/proc/version").read_text(encoding="utf-8", errors="ignore").lower()
                is_wsl = bool(os.getenv("WSL_INTEROP") or os.getenv("WSL_DISTRO_NAME") or "microsoft" in proc_version)
                runserver_host = "0.0.0.0" if is_wsl else "127.0.0.1"
            sys.argv.append(f"{runserver_host}:{default_port}")

    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
