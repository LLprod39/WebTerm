from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("kubernetes_ops", "0018_alter_k8sactionrequest_action_apply"),
    ]

    operations = [
        migrations.AddField(
            model_name="k8sprovider",
            name="created_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="k8s_providers",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddIndex(
            model_name="k8sprovider",
            index=models.Index(fields=["created_by", "kind"], name="k8s_provider_owner_kind_idx"),
        ),
    ]
