"""
Создание тестовых групп серверов и серверов для проверки фронтенда.
Использование: python manage.py seed_servers_for_frontend [--username USER]
Без --username берётся первый суперпользователь.
"""
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from servers.models import Server, ServerGroup

User = get_user_model()


# Пары (название группы, цвет, описание)
GROUPS = [
    ("Продакшен", "#22c55e", "Серверы продакшен-окружения"),
    ("Тестовый стенд", "#f59e0b", "Стенд для тестов и разработки"),
]

# Серверы: (name, host, port, username, server_type, group_index)
# group_index: 0 = первая группа, 1 = вторая
SERVERS = [
    ("app-prod-01", "192.168.1.10", 22, "deploy", "ssh", 0),
    ("app-prod-02", "192.168.1.11", 22, "deploy", "ssh", 0),
    ("db-prod", "192.168.1.20", 22, "postgres", "ssh", 0),
    ("test-web-01", "10.0.0.101", 22, "dev", "ssh", 1),
    ("test-web-02", "10.0.0.102", 22, "dev", "ssh", 1),
    ("test-rdp-win", "10.0.0.201", 3389, "administrator", "rdp", 1),
]


class Command(BaseCommand):
    help = "Создаёт пару групп серверов и тестовые серверы для проверки фронтенда."

    def add_arguments(self, parser):
        parser.add_argument(
            "--username",
            type=str,
            default=None,
            help="Пользователь, которому создаются группы и серверы. По умолчанию — первый суперпользователь.",
        )
        parser.add_argument(
            "--noinput",
            action="store_true",
            help="Не спрашивать подтверждение при существующих группах.",
        )

    def handle(self, *args, **options):
        username = options["username"]
        noinput = options["noinput"]

        if username:
            user = User.objects.filter(username=username).first()
            if not user:
                self.stderr.write(self.style.ERROR(f"Пользователь '{username}' не найден."))
                return
        else:
            user = User.objects.filter(is_superuser=True).order_by("pk").first()
            if not user:
                self.stderr.write(
                    self.style.ERROR("Нет суперпользователей. Создайте: python manage.py createsuperuser")
                )
                return

        self.stdout.write(f"Пользователь: {user.username} (pk={user.pk})")

        existing = ServerGroup.objects.filter(user=user, name__in=[g[0] for g in GROUPS])
        if existing.exists() and not noinput:
            confirm = input(
                "Группы с такими именами уже есть у пользователя. Пересоздать серверы в них? [y/N]: "
            )
            if confirm.lower() != "y":
                self.stdout.write("Отменено.")
                return

        groups = []
        for name, color, description in GROUPS:
            group, created = ServerGroup.objects.get_or_create(
                user=user,
                name=name,
                defaults={"description": description, "color": color},
            )
            if created:
                self.stdout.write(self.style.SUCCESS(f"  Группа: {group.name}"))
            groups.append(group)

        created_count = 0
        for name, host, port, username_val, server_type, group_idx in SERVERS:
            group = groups[group_idx]
            _, created = Server.objects.get_or_create(
                user=user,
                name=name,
                defaults={
                    "group": group,
                    "host": host,
                    "port": port,
                    "username": username_val,
                    "server_type": server_type,
                    "auth_method": "password",
                    "encrypted_password": "",
                    "notes": "Тестовый сервер для фронтенда",
                    "is_active": True,
                },
            )
            if created:
                created_count += 1
                self.stdout.write(self.style.SUCCESS(f"  Сервер: {name} -> {group.name}"))

        self.stdout.write(self.style.SUCCESS(f"Готово. Создано серверов: {created_count}, групп: {len(groups)}."))
