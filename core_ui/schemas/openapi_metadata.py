"""Small view metadata helpers consumed by the generated OpenAPI document."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any


def openapi_responses(
    responses: Mapping[int | str, Mapping[str, Any] | None],
):
    """Attach additive/override response metadata to a Django view."""

    def decorate(view: Callable[..., Any]) -> Callable[..., Any]:
        view.openapi_responses = {str(status): value for status, value in responses.items()}  # type: ignore[attr-defined]
        return view

    return decorate
