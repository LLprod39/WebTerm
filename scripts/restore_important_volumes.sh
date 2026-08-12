#!/usr/bin/env bash
# Validate or restore the encrypted media/config/playbook-bundle archive.
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ARCHIVE_PATH="${1:-}"
COMPOSE_FILE="${COMPOSE_FILE:-$ROOT_DIR/docker-compose.production.yml}"
COMPOSE_OVERRIDE_FILE="${COMPOSE_OVERRIDE_FILE:-}"
ENV_FILE="${ENV_FILE:-$ROOT_DIR/.env.production}"
PROJECT_NAME="${PROJECT_NAME:-mini-prod}"
SERVICE="${VOLUME_RESTORE_SERVICE:-backend}"
AGE_IDENTITY_FILE="${BACKUP_AGE_IDENTITY_FILE:-}"
DRY_RUN="${RESTORE_DRY_RUN:-0}"
CONFIRMATION="${RESTORE_CONFIRM:-}"

compose() {
  local compose_files=(-f "$COMPOSE_FILE")
  if [[ -n "$COMPOSE_OVERRIDE_FILE" ]]; then
    compose_files+=(-f "$COMPOSE_OVERRIDE_FILE")
  fi
  docker compose \
    --project-name "$PROJECT_NAME" \
    --env-file "$ENV_FILE" \
    "${compose_files[@]}" \
    "$@"
}

if [[ -z "$ARCHIVE_PATH" || ! -f "$ARCHIVE_PATH" ]]; then
  echo "Usage: $0 /path/to/webterm_volumes_YYYYMMDDTHHMMSSZ.tar.gz.age" >&2
  exit 1
fi
if ! command -v age >/dev/null 2>&1; then
  echo "age is required to decrypt important-volume backups" >&2
  exit 1
fi
if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 is required to validate important-volume backups" >&2
  exit 1
fi
if [[ -z "$AGE_IDENTITY_FILE" || ! -f "$AGE_IDENTITY_FILE" ]]; then
  echo "BACKUP_AGE_IDENTITY_FILE must reference the protected age identity file" >&2
  exit 1
fi
if find "$AGE_IDENTITY_FILE" -prune -perm /077 -print -quit | grep -q .; then
  echo "BACKUP_AGE_IDENTITY_FILE must not be accessible by group or other users" >&2
  exit 1
fi
if [[ ! -f "$COMPOSE_FILE" || ! -f "$ENV_FILE" ]]; then
  echo "Compose file and production environment are required" >&2
  exit 1
fi
if [[ -n "$COMPOSE_OVERRIDE_FILE" && ! -f "$COMPOSE_OVERRIDE_FILE" ]]; then
  echo "Compose override not found: $COMPOSE_OVERRIDE_FILE" >&2
  exit 1
fi
if [[ ! -f "$ARCHIVE_PATH.sha256" ]]; then
  echo "Encrypted important-volume checksum file is required" >&2
  exit 1
fi

echo "Validating encrypted important-volume archive"
(
  cd "$(dirname "$ARCHIVE_PATH")"
  sha256sum --check "$(basename "$ARCHIVE_PATH").sha256"
)
age --decrypt --identity "$AGE_IDENTITY_FILE" "$ARCHIVE_PATH" \
  | python3 -c '
import pathlib
import sys
import tarfile

allowed = (
    pathlib.PurePosixPath("media"),
    pathlib.PurePosixPath("config_runtime"),
    pathlib.PurePosixPath("private/playbook_bundles"),
)

with tarfile.open(fileobj=sys.stdin.buffer, mode="r|gz") as archive:
    seen = set()
    for member in archive:
        path = pathlib.PurePosixPath(member.name)
        if path.is_absolute() or ".." in path.parts:
            raise SystemExit("archive contains an unsafe path")
        if not any(path == root or root in path.parents for root in allowed):
            raise SystemExit("archive contains a path outside the approved volumes")
        if not (member.isfile() or member.isdir()):
            raise SystemExit("archive contains a link or special filesystem entry")
        for root in allowed:
            if path == root or root in path.parents:
                seen.add(root)
    if seen != set(allowed):
        raise SystemExit("archive does not contain every required volume root")
'

if [[ "$DRY_RUN" == "1" ]]; then
  echo "Archive is valid; dry run did not change the important volumes"
  exit 0
fi
if [[ "$CONFIRMATION" != "RESTORE_WEBTERM_VOLUMES" ]]; then
  echo "Restore replaces volume contents. Set RESTORE_CONFIRM=RESTORE_WEBTERM_VOLUMES for the intended isolated target." >&2
  exit 1
fi

# Any running Compose container that mounts one of the target paths can race an
# extraction. Require an operator-controlled maintenance window instead of
# stopping services implicitly.
while IFS= read -r container_id; do
  [[ -n "$container_id" ]] || continue
  if docker inspect --format '{{range .Mounts}}{{println .Destination}}{{end}}' "$container_id" \
    | grep -Eq '^/workspace/(media|config_runtime|private/playbook_bundles)$'; then
    echo "A running Compose service mounts an important volume; stop writers before restore" >&2
    exit 1
  fi
done < <(compose ps -q)

# Recheck immediately before the destructive phase. The helper container uses
# only project-scoped named volumes and no dependencies or network services.
(
  cd "$(dirname "$ARCHIVE_PATH")"
  sha256sum --check "$(basename "$ARCHIVE_PATH").sha256"
)
echo "Replacing media, runtime config and private playbook bundles"
age --decrypt --identity "$AGE_IDENTITY_FILE" "$ARCHIVE_PATH" \
  | compose run --rm --no-deps -T --entrypoint sh "$SERVICE" -ec '
      set -eu
      for root in media config_runtime private/playbook_bundles; do
        test -d "/workspace/$root"
        find "/workspace/$root" -xdev -mindepth 1 -delete
      done
      exec tar -xzf - -C /workspace \
        --no-same-owner --no-same-permissions --delay-directory-restore
    '

echo "Important-volume restore finished"
echo "AI CLI credential volumes, logs and telemetry were intentionally excluded; re-authenticate Codex/Grok connections."
