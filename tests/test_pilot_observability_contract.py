from __future__ import annotations

import json
import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
METRIC = re.compile(r"\bwebterm_[a-z][a-z0-9_]*\b")


def _webterm_metrics(text: str) -> set[str]:
    return set(METRIC.findall(text))


def _exported_or_recorded_metrics() -> set[str]:
    exported: set[str] = set()
    for relative in (
        "app/prometheus_registry.py",
        "servers/prometheus_metrics.py",
        "core_ui/prometheus_metrics.py",
        "studio/prometheus_metrics.py",
    ):
        exported.update(_webterm_metrics((ROOT / relative).read_text(encoding="utf-8")))

    observability = (ROOT / "app/observability.py").read_text(encoding="utf-8")
    for dotted in re.findall(r'create_counter\(\s*"(webterm\.[a-z0-9_.]+)"', observability):
        exported.add(dotted.replace(".", "_") + "_total")

    collector = yaml.safe_load((ROOT / "docker/observability/otel-collector.yml").read_text(encoding="utf-8"))
    for connector in (collector.get("connectors") or {}).values():
        for metric in connector.get("logs", []):
            name = str(metric.get("name") or "")
            if name.startswith("webterm."):
                exported.add(name.replace(".", "_"))

    rules = yaml.safe_load((ROOT / "docker/observability/prometheus-alerts.yml").read_text(encoding="utf-8"))
    for group in rules.get("groups", []):
        for rule in group.get("rules", []):
            record = str(rule.get("record") or "")
            if record.startswith("webterm_"):
                exported.add(record)
    return exported


def test_every_webterm_dashboard_and_alert_metric_has_a_real_export_contract() -> None:
    dashboard_text = (ROOT / "docker/observability/grafana/dashboards/pilot-overview.json").read_text(encoding="utf-8")
    alerts_text = (ROOT / "docker/observability/prometheus-alerts.yml").read_text(encoding="utf-8")
    referenced = _webterm_metrics(dashboard_text + "\n" + alerts_text)
    missing = sorted(referenced - _exported_or_recorded_metrics())

    assert not missing, f"dashboard/alert metrics are not exported or recorded: {missing}"


def test_pilot_dashboard_uses_agent_capacity_not_operator_queue() -> None:
    dashboard = json.loads(
        (ROOT / "docker/observability/grafana/dashboards/pilot-overview.json").read_text(encoding="utf-8")
    )
    expressions = "\n".join(
        target.get("expr", "") for panel in dashboard["panels"] for target in panel.get("targets", [])
    )

    assert "webterm_agent_queue_depth" in expressions
    assert "webterm_agent_queue_oldest_age_seconds" in expressions
    assert "webterm_agent_execution_workers" in expressions
    assert "webterm_operator_queue" not in expressions


def test_observability_profile_retention_and_backup_signal_are_privacy_safe() -> None:
    compose = (ROOT / "docker-compose.production.yml").read_text(encoding="utf-8")
    collector = (ROOT / "docker/observability/otel-collector.yml").read_text(encoding="utf-8")
    loki = (ROOT / "docker/observability/loki.yml").read_text(encoding="utf-8")
    tempo = (ROOT / "docker/observability/tempo.yml").read_text(encoding="utf-8")

    assert "--storage.tsdb.retention.time=${PROMETHEUS_RETENTION:-30d}" in compose
    assert "LOKI_RETENTION_PERIOD" in compose
    assert "TEMPO_RETENTION" in compose
    assert "last_success.unixtime" in collector
    assert "last_failure.unixtime" in collector
    assert "message removed by pilot privacy policy" in collector
    assert "prompts" not in collector.lower()
    assert "credential contents" not in collector.lower()
    assert "${LOKI_RETENTION_PERIOD}" in loki
    assert "${TEMPO_RETENTION}" in tempo


def test_alerts_route_to_a_secret_backed_alertmanager_receiver() -> None:
    compose = (ROOT / "docker-compose.production.yml").read_text(encoding="utf-8")
    prometheus = yaml.safe_load((ROOT / "docker/observability/prometheus.yml").read_text(encoding="utf-8"))
    alertmanager = yaml.safe_load((ROOT / "docker/observability/alertmanager.yml").read_text(encoding="utf-8"))
    installer = (ROOT / "docker/install-production.sh").read_text(encoding="utf-8")

    targets = prometheus["alerting"]["alertmanagers"][0]["static_configs"][0]["targets"]
    webhook = alertmanager["receivers"][0]["webhook_configs"][0]
    assert targets == ["alertmanager:9093"]
    assert webhook["url_file"] == "/run/secrets/alertmanager_webhook_url"
    assert webhook["send_resolved"] is True
    assert "WEBTERM_ALERTMANAGER_IMAGE" in compose
    assert "quay.io/prometheus/alertmanager:main@sha256:" in compose
    assert "ALERTMANAGER_WEBHOOK_URL_FILE must reference a non-symlink" in installer
    assert "ALERTMANAGER_WEBHOOK_URL_FILE must be owned by runtime UID 65534" in installer


def test_observability_images_are_immutable_and_share_the_high_critical_ci_gate() -> None:
    compose = (ROOT / "docker-compose.production.yml").read_text(encoding="utf-8")
    example = (ROOT / ".env.production.example").read_text(encoding="utf-8")
    security = (ROOT / ".github/workflows/security.yml").read_text(encoding="utf-8")
    refs = (
        "otel/opentelemetry-collector-contrib:0.158.0@sha256:c5918f78992ee73b0d6f0e599423ac5ec52dd5d9726733114d6eca53d5a32ed5",
        "prom/prometheus:v3.13.2-distroless@sha256:64f71bb84e03c855948418b0fc5dea53e9543d8e3fc9931598f583805507f05e",
        "quay.io/prometheus/alertmanager:main@sha256:a42c3e2e8f7cd4fd3a0ce1bd593ca5abe965c97b993476007d6f69c4a2aa33b5",
        "grafana/grafana:nightly-distroless-slim@sha256:b2c2fd5391216bd57e6bad74c0dce05f8e275479e1153ab57149a4f019a3dceb",
        "grafana/tempo:main-1a8b052-2010-1@sha256:78dc87894e9eb054b0229980ac3e7f099b437aec07a8731612373fc09b7f8ba0",
        "grafana/loki:3.7.6@sha256:efd47c67f9bac88ca29bcf8cb997d9ab29d1848bd0aff579282295542a745952",
    )

    for ref in refs:
        assert ref in compose
        assert ref in example
        assert ref in security
    assert "--exit-code 1" in security
    assert "--severity HIGH,CRITICAL" in security
    assert "--ignore-unfixed" in security
    assert "--skip-files" not in security
    assert "--skip-dirs" not in security


def test_encrypted_backup_and_restore_timers_fail_closed() -> None:
    backup = (ROOT / "scripts/backup_postgres.sh").read_text(encoding="utf-8")
    restore = (ROOT / "scripts/restore_postgres.sh").read_text(encoding="utf-8")
    restore_volumes = (ROOT / "scripts/restore_important_volumes.sh").read_text(encoding="utf-8")
    restore_test = (ROOT / "docker/systemd/verify-latest-encrypted-backup.sh").read_text(encoding="utf-8")
    backup_timer = (ROOT / "docker/systemd/webterm-postgres-backup.timer").read_text(encoding="utf-8")
    restore_timer = (ROOT / "docker/systemd/webterm-postgres-restore-test.timer").read_text(encoding="utf-8")

    assert "webterm_${STAMP}.dump.age" in backup
    assert "age --encrypt --recipients-file" in backup
    assert "mkfifo -m 600" in backup
    assert 'OUT_FILE="$BACKUP_DIR/webterm_${STAMP}.dump"' not in backup
    assert "BACKUP_AGE_RECIPIENT_FILE must reference" in backup
    assert "webterm_volumes_${STAMP}.tar.gz.age" in backup
    assert "media config_runtime private/playbook_bundles" in backup
    assert "mini_prod_logs" not in backup
    assert "credential" not in backup.lower()
    assert "age --decrypt --identity" in restore
    assert "Encrypted backup checksum file is required" in restore
    assert "RESTORE_CONFIRM=RESTORE_WEBTERM" in restore
    assert "age --decrypt --identity" in restore_volumes
    assert "RESTORE_WEBTERM_VOLUMES" in restore_volumes
    assert "archive contains a link or special filesystem entry" in restore_volumes
    assert "re-authenticate Codex/Grok" in restore_volumes
    assert "restore_important_volumes.sh" in restore_test
    assert "OnCalendar=*-*-* 02:30:00 UTC" in backup_timer
    assert "OnCalendar=Sun *-*-* 04:30:00 UTC" in restore_timer
    assert "Persistent=true" in backup_timer
    assert "Persistent=true" in restore_timer
