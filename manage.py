#!/usr/bin/env python
"""Django's command-line utility for administrative tasks."""
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
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'web_ui.settings')
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Are you sure it's installed and "
            "available on your PYTHONPATH environment variable? Did you "
            "forget to activate a virtual environment?"
        ) from exc

    # Если запускается runserver без указания порта, используем порт из переменной окружения или 9000
    if len(sys.argv) >= 2 and sys.argv[1] == 'runserver' and len(sys.argv) == 2:
        default_port = os.getenv('DJANGO_PORT', '9000')
        sys.argv.append(default_port)

    execute_from_command_line(sys.argv)


if __name__ == '__main__':
    main()
