from functools import lru_cache

from django.http import JsonResponse
from django.views.decorators.http import require_GET

from core_ui.schemas.openapi import build_openapi_document


@lru_cache(maxsize=1)
def _document():
    return build_openapi_document()


@require_GET
def api_openapi(request):
    """Return the generated OpenAPI 3.1 document."""
    return JsonResponse(_document())
