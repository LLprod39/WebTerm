#!/usr/bin/env bash

installer_secret_error() {
  printf 'Error: %s\n' "$*" >&2
  return 1
}

installer_read_private_file() {
  local secret_file="$1"
  local mode
  if [[ -L "$secret_file" ]]; then
    installer_secret_error "refusing symbolic-link secret file: $secret_file"
    return 1
  fi
  if [[ ! -f "$secret_file" ]]; then
    installer_secret_error "secret file not found: $secret_file"
    return 1
  fi
  mode="$(stat -c '%a' "$secret_file")"
  if (( (8#$mode & 077) != 0 )); then
    installer_secret_error "secret file must not be readable or writable by group/others: $secret_file"
    return 1
  fi
  python3 - "$secret_file" <<'PY'
from pathlib import Path
import sys

data = Path(sys.argv[1]).read_bytes()
if data.endswith(b"\r\n"):
    data = data[:-2]
elif data.endswith(b"\n"):
    data = data[:-1]
if not data or b"\x00" in data or b"\r" in data or b"\n" in data:
    raise SystemExit("secret file must contain exactly one non-empty line")
sys.stdout.write(data.decode("utf-8"))
PY
}

installer_read_secret() {
  local target_name="$1"
  local label="$2"
  local source_kind="${3:-}"
  local source_file="${4:-}"
  local value=""
  local confirmation=""
  local extra=""

  case "$source_kind" in
    stdin)
      if ! IFS= read -r value; then
        [[ -n "$value" ]] || {
          installer_secret_error "$label was not provided on stdin"
          return 1
        }
      fi
      if IFS= read -r extra; then
        installer_secret_error "$label stdin must contain exactly one line"
        return 1
      fi
      ;;
    file)
      value="$(installer_read_private_file "$source_file")" || return 1
      ;;
    "")
      if [[ ! -t 0 ]]; then
        installer_secret_error "$label requires a TTY or an explicit stdin/private-file source"
        return 1
      fi
      printf '%s: ' "$label" >/dev/tty
      IFS= read -r -s value </dev/tty
      printf '\nConfirm %s: ' "$label" >/dev/tty
      IFS= read -r -s confirmation </dev/tty
      printf '\n' >/dev/tty
      if [[ "$value" != "$confirmation" ]]; then
        installer_secret_error "$label confirmation does not match"
        return 1
      fi
      ;;
    *)
      installer_secret_error "unsupported secret source: $source_kind"
      return 1
      ;;
  esac

  if [[ -z "$value" ]]; then
    installer_secret_error "$label must not be empty"
    return 1
  fi
  printf -v "$target_name" '%s' "$value"
}
