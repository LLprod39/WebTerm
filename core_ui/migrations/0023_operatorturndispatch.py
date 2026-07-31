from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("core_ui", "0022_projects")]

    operations = [
        migrations.CreateModel(
            name="OperatorTurnDispatch",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("kind", models.CharField(choices=[("message", "Message"), ("action", "Action")], max_length=16)),
                ("payload", models.JSONField(blank=True, default=dict)),
                ("status", models.CharField(choices=[("queued", "Queued"), ("claimed", "Claimed"), ("completed", "Completed"), ("failed", "Failed"), ("canceled", "Canceled")], default="queued", max_length=16)),
                ("queued_at", models.DateTimeField(auto_now_add=True)),
                ("claimed_at", models.DateTimeField(blank=True, null=True)),
                ("heartbeat_at", models.DateTimeField(blank=True, null=True)),
                ("lease_expires_at", models.DateTimeField(blank=True, null=True)),
                ("completed_at", models.DateTimeField(blank=True, null=True)),
                ("claimed_by", models.CharField(blank=True, max_length=120)),
                ("attempt_count", models.PositiveSmallIntegerField(default=0)),
                ("max_attempts", models.PositiveSmallIntegerField(default=3)),
                ("error", models.TextField(blank=True)),
                ("action", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="turn_dispatches", to="core_ui.assistantaction")),
                ("session", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="turn_dispatches", to="core_ui.chatsession")),
                ("turn", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="dispatches", to="core_ui.chatturnstate")),
            ],
            options={"ordering": ["queued_at", "id"]},
        ),
        migrations.AddIndex(model_name="operatorturndispatch", index=models.Index(fields=["status", "queued_at"], name="cu_opdispatch_status_idx")),
        migrations.AddIndex(model_name="operatorturndispatch", index=models.Index(fields=["session", "status"], name="cu_opdispatch_session_idx")),
        migrations.AddConstraint(model_name="operatorturndispatch", constraint=models.CheckConstraint(condition=models.Q(("max_attempts__gte", 1)), name="cu_opdispatch_attempts_gte_1")),
        migrations.AddConstraint(model_name="operatorturndispatch", constraint=models.UniqueConstraint(condition=models.Q(("status__in", ["queued", "claimed"])), fields=("session",), name="cu_opdispatch_one_active_session")),
    ]
