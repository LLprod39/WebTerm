"""
Create a ready-to-run "Server Update with Human Approval" pipeline for a user.

Usage:
    python manage.py setup_server_update_pipeline
    python manage.py setup_server_update_pipeline --username myuser

- Loads/updates pipeline templates.
- Creates a pipeline from template "server-update-approval" (server backup-01 or first available).
- Prints pipeline ID and instructions to run it in Studio.
"""

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import BaseCommand

from studio.models import PipelineTemplate


class Command(BaseCommand):
    help = "Create Server Update with Human Approval pipeline for quick test"

    def add_arguments(self, parser):
        parser.add_argument(
            "--username",
            type=str,
            default=None,
            help="User to own the pipeline (default: first superuser)",
        )

    def handle(self, *args, **options):
        User = get_user_model()
        username = options.get("username")
        if username:
            user = User.objects.filter(username=username).first()
            if not user:
                self.stderr.write(self.style.ERROR(f"User '{username}' not found."))
                return
        else:
            user = User.objects.filter(is_superuser=True).order_by("id").first()
            if not user:
                user = User.objects.order_by("id").first()
            if not user:
                self.stderr.write(self.style.ERROR("No user in database. Create one with createsuperuser."))
                return

        call_command("load_pipeline_templates", "--force")
        tpl = PipelineTemplate.objects.filter(slug="server-update-approval").first()
        if not tpl:
            self.stderr.write(self.style.ERROR("Template 'server-update-approval' not found."))
            return

        pipeline = tpl.instantiate_for_user(user)
        self.stdout.write(
            self.style.SUCCESS(
                f"Pipeline \"{pipeline.name}\" created (ID={pipeline.id}) for user {user.username}."
            )
        )
        self.stdout.write("")
        self.stdout.write("Next steps:")
        self.stdout.write('  1. Open Studio -> Pipelines -> open "Server Update with Human Approval".')
        self.stdout.write("  2. Click Run. Pipeline: discover server -> build plan -> wait for your approval.")
        self.stdout.write('  3. When it stops at "Await Your Approval", open the run panel and use the APPROVE link.')
        self.stdout.write("  4. After 1 minute wait it will apply updates and verify services.")
        self.stdout.write("")
        self.stdout.write(f"  Direct link (if frontend at /studio): /studio/pipelines/{pipeline.id}")
