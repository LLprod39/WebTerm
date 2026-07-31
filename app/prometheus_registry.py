"""Dependency-inversion registry for feature-owned Prometheus collectors."""

from __future__ import annotations

from collections.abc import Callable

PrometheusProvider = Callable[[], list[str]]
_providers: dict[str, PrometheusProvider] = {}


def register_prometheus_provider(name: str, provider: PrometheusProvider | None) -> None:
    key = str(name or "").strip()
    if not key:
        raise ValueError("Prometheus provider name is required")
    if provider is None:
        _providers.pop(key, None)
    else:
        _providers[key] = provider


def collect_prometheus_lines() -> list[str]:
    lines: list[str] = []
    for name in sorted(_providers):
        try:
            lines.extend(str(line) for line in _providers[name]())
        except Exception:
            lines.extend(
                [
                    f'# HELP webterm_metrics_provider_up Whether the "{name}" metrics provider succeeded.',
                    "# TYPE webterm_metrics_provider_up gauge",
                    f'webterm_metrics_provider_up{{provider="{name}"}} 0',
                ]
            )
    return lines
