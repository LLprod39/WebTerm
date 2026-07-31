from django.http import HttpResponse
from django.views.decorators.http import require_GET

from app.observability import prometheus_metrics_text


@require_GET
def prometheus_metrics(request):
    return HttpResponse(
        prometheus_metrics_text(),
        content_type="text/plain; version=0.0.4; charset=utf-8",
    )
