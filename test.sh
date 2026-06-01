#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_DIR="${VENV_DIR:-$ROOT_DIR/.venv_v4}"
ENV_FILE="${ENV_FILE:-$ROOT_DIR/.env}"
DB_NAME="${DB_NAME:-trading_bot}"
DB_USER="${DB_USER:-trading_bot}"
DB_PASSWORD="${DB_PASSWORD:-trading_bot}"
POSTGRES_HOST="${POSTGRES_HOST:-127.0.0.1}"
POSTGRES_PORT="${POSTGRES_PORT:-5432}"
INSTALL_INTERFACE_DEPS="${INSTALL_INTERFACE_DEPS:-1}"
SETUP_POSTGRES="${SETUP_POSTGRES:-1}"
RESET_POSTGRES_DATA="${RESET_POSTGRES_DATA:-0}"
PYTHON312_VERSION="${PYTHON312_VERSION:-3.12.11}"
PYENV_ROOT="${PYENV_ROOT:-$HOME/.pyenv}"
PACMAN_PACKAGES=(
  base-devel
  git
  zsh
  make
  lsof
  python
  python-pip
  pkgconf
  pyenv
  openssl
  xz
  tk
  libffi
  sqlite
  postgresql
  postgresql-libs
  bun
)

log() {
  printf '[prepare-arch] %s\n' "$*"
}

fail() {
  printf '[prepare-arch] ERROR: %s\n' "$*" >&2
  exit 1
}

need_cmd() {
  command -v "$1" >/dev/null 2>&1 || fail "Missing required command: $1"
}

run_sudo() {
  if [[ "${EUID}" -eq 0 ]]; then
    "$@"
  else
    sudo "$@"
  fi
}

run_as_postgres() {
  if [[ "${EUID}" -eq 0 ]]; then
    su - postgres -s /bin/bash -c "$*"
  else
    sudo -u postgres bash -lc "$*"
  fi
}

sudo_sh() {
  if [[ "${EUID}" -eq 0 ]]; then
    bash -lc "$*"
  else
    sudo bash -lc "$*"
  fi
}

ensure_arch() {
  if [[ ! -f /etc/os-release ]]; then
    fail "Cannot detect operating system. This script is intended for Arch Linux."
  fi
  # shellcheck disable=SC1091
  source /etc/os-release
  if [[ "${ID:-}" != "arch" && " ${ID_LIKE:-} " != *" arch "* ]]; then
    fail "Detected ${PRETTY_NAME:-unknown}. This script is intended for Arch Linux."
  fi
}

install_packages() {
  need_cmd pacman
  log "Installing Arch packages: ${PACMAN_PACKAGES[*]}"
  run_sudo pacman -Sy --needed --noconfirm "${PACMAN_PACKAGES[@]}"
}

resolve_python312_bin() {
  if command -v python3.12 >/dev/null 2>&1; then
    python3.12 -c 'import sys; raise SystemExit(0 if sys.version_info[:2] == (3, 12) else 1)' >/dev/null 2>&1 && {
      command -v python3.12
      return 0
    }
  fi

  local pyenv_python="$PYENV_ROOT/versions/$PYTHON312_VERSION/bin/python3.12"
  if [[ -x "$pyenv_python" ]]; then
    "$pyenv_python" -c 'import sys; raise SystemExit(0 if sys.version_info[:2] == (3, 12) else 1)' >/dev/null 2>&1 && {
      printf '%s\n' "$pyenv_python"
      return 0
    }
  fi

  local pyenv_python_generic="$PYENV_ROOT/versions/$PYTHON312_VERSION/bin/python"
  if [[ -x "$pyenv_python_generic" ]]; then
    "$pyenv_python_generic" -c 'import sys; raise SystemExit(0 if sys.version_info[:2] == (3, 12) else 1)' >/dev/null 2>&1 && {
      printf '%s\n' "$pyenv_python_generic"
      return 0
    }
  fi

  return 1
}

install_python312() {
  if resolve_python312_bin >/dev/null 2>&1; then
    log "Python 3.12 already available"
    return 0
  fi

  need_cmd pyenv
  export PYENV_ROOT
  export PATH="$PYENV_ROOT/bin:$PATH"
  eval "$(pyenv init -)"
  log "Installing Python $PYTHON312_VERSION with pyenv"
  pyenv install -s "$PYTHON312_VERSION"

  if ! resolve_python312_bin >/dev/null 2>&1; then
    fail "Python $PYTHON312_VERSION was installed by pyenv but could not be resolved at $PYENV_ROOT/versions/$PYTHON312_VERSION/bin/python3.12"
  fi
}

create_virtualenv() {
  local py_bin="$1"
  if [[ ! -x "$VENV_DIR/bin/python" ]] || ! "$VENV_DIR/bin/python" -c 'import sys; raise SystemExit(0 if sys.version_info[:2] == (3, 12) else 1)' >/dev/null 2>&1; then
    log "Creating virtual environment at $VENV_DIR with $py_bin"
    rm -rf "$VENV_DIR"
    "$py_bin" -m venv "$VENV_DIR"
  else
    log "Reusing existing Python 3.12 virtual environment at $VENV_DIR"
  fi

  log "Upgrading pip/setuptools/wheel"
  "$VENV_DIR/bin/python" -m pip install --upgrade pip setuptools wheel

  log "Installing runtime + V6 Python dependencies"
  "$VENV_DIR/bin/pip" install -r "$ROOT_DIR/runtime/requirements.txt" -r "$ROOT_DIR/requirements-v5.txt"
}

install_interface_deps() {
  if [[ "$INSTALL_INTERFACE_DEPS" != "1" ]]; then
    log "Skipping interface dependency installation (INSTALL_INTERFACE_DEPS=$INSTALL_INTERFACE_DEPS)"
    return 0
  fi
  if [[ -f "$ROOT_DIR/interface/package.json" ]]; then
    log "Installing interface dependencies with bun"
    (cd "$ROOT_DIR/interface" && bun install)
  fi
}

ensure_env_file() {
  if [[ ! -f "$ENV_FILE" ]]; then
    if [[ -f "$ROOT_DIR/.env.example" ]]; then
      log "Creating $ENV_FILE from .env.example"
      cp "$ROOT_DIR/.env.example" "$ENV_FILE"
    else
      log "Creating $ENV_FILE"
      cat >"$ENV_FILE" <<EOF
V4_DATABASE_URL=postgresql://${DB_USER}:${DB_PASSWORD}@${POSTGRES_HOST}:${POSTGRES_PORT}/${DB_NAME}
V6_DATABASE_URL=postgresql://${DB_USER}:${DB_PASSWORD}@${POSTGRES_HOST}:${POSTGRES_PORT}/${DB_NAME}
DATABASE_URL=postgresql://${DB_USER}:${DB_PASSWORD}@${POSTGRES_HOST}:${POSTGRES_PORT}/${DB_NAME}
BACKEND_PORT=8000
INTERFACE_PORT=5173
EOF
    fi
  fi

  local v4_db_url="V4_DATABASE_URL=postgresql://${DB_USER}:${DB_PASSWORD}@${POSTGRES_HOST}:${POSTGRES_PORT}/${DB_NAME}"
  local v6_db_url="V6_DATABASE_URL=postgresql://${DB_USER}:${DB_PASSWORD}@${POSTGRES_HOST}:${POSTGRES_PORT}/${DB_NAME}"
  local generic_db_url="DATABASE_URL=postgresql://${DB_USER}:${DB_PASSWORD}@${POSTGRES_HOST}:${POSTGRES_PORT}/${DB_NAME}"
  python - <<PY
from pathlib import Path
path = Path(${ENV_FILE@Q})
text = path.read_text() if path.exists() else ""
lines = text.splitlines()
updates = {
    'V4_DATABASE_URL=': ${v4_db_url@Q},
    'V6_DATABASE_URL=': ${v6_db_url@Q},
    'DATABASE_URL=': ${generic_db_url@Q},
}
seen = {key: False for key in updates}
out = []
for line in lines:
    replaced = False
    for prefix, value in updates.items():
        if line.startswith(prefix) and not seen[prefix]:
            out.append(value)
            seen[prefix] = True
            replaced = True
            break
        elif line.startswith(prefix):
            replaced = True
            break
    if not replaced:
        out.append(line)
for prefix, value in updates.items():
    if not seen[prefix]:
        out.append(value)
path.write_text('\n'.join(out) + ('\n' if out else ''))
PY
  log "Configured $ENV_FILE"
}

setup_postgres() {
  if [[ "$SETUP_POSTGRES" != "1" ]]; then
    log "Skipping PostgreSQL setup (SETUP_POSTGRES=$SETUP_POSTGRES)"
    return 0
  fi

  need_cmd systemctl
  if id postgres >/dev/null 2>&1; then
    if [[ "$RESET_POSTGRES_DATA" == "1" ]]; then
      log "RESET_POSTGRES_DATA=1, removing existing PostgreSQL data directory"
      run_sudo systemctl stop postgresql || true
      sudo_sh "rm -rf /var/lib/postgres/data && install -d -o postgres -g postgres /var/lib/postgres /var/lib/postgres/data"
    fi

    if sudo_sh "test -f /var/lib/postgres/data/PG_VERSION"; then
      log "PostgreSQL data directory already initialized"
    elif sudo_sh "test -d /var/lib/postgres/data && find /var/lib/postgres/data -mindepth 1 -maxdepth 1 | read"; then
      log "PostgreSQL data directory exists and is not empty; skipping initdb"
      log "If PostgreSQL fails to start, inspect /var/lib/postgres/data or rerun with RESET_POSTGRES_DATA=1"
    else
      log "Initializing PostgreSQL data directory"
      run_sudo install -d -o postgres -g postgres /var/lib/postgres /var/lib/postgres/data
      run_as_postgres "initdb -D /var/lib/postgres/data"
    fi
  fi

  log "Enabling and starting PostgreSQL service"
  run_sudo systemctl enable --now postgresql

  if command -v psql >/dev/null 2>&1; then
    log "Ensuring PostgreSQL role/database exist"
    run_as_postgres "psql -v ON_ERROR_STOP=1 postgres <<'SQL'
DO
\$\$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '${DB_USER}') THEN
        CREATE ROLE ${DB_USER} LOGIN PASSWORD '${DB_PASSWORD}';
    ELSE
        ALTER ROLE ${DB_USER} WITH LOGIN PASSWORD '${DB_PASSWORD}';
    END IF;
END
\$\$;
SQL"
    if ! run_as_postgres "psql -tAc \"SELECT 1 FROM pg_database WHERE datname='${DB_NAME}'\" postgres" | grep -q 1; then
      run_as_postgres "createdb -O '${DB_USER}' '${DB_NAME}'"
    fi
  fi
}

print_summary() {
  cat <<EOF

Environment preparation finished.

Python env:
  ${VENV_DIR}
  ${VENV_DIR}/bin/python

Environment file:
  ${ENV_FILE}

Useful next steps:
  make v6-install
  make start
  make v6-stack-up

Python pinned for this repo:
  ${PYTHON312_VERSION}

If you want to skip PostgreSQL setup next time:
  SETUP_POSTGRES=0 make prepare-arch-enviroment

If PostgreSQL data is broken and you want a clean reset:
  RESET_POSTGRES_DATA=1 make prepare-arch-enviroment
EOF
}

main() {
  ensure_arch
  install_packages

  install_python312

  local py_bin
  py_bin="$(resolve_python312_bin || true)"
  [[ -n "$py_bin" ]] || fail "Could not find Python 3.12. Re-run with pyenv installed or install python3.12 manually."
  log "Using Python interpreter: $py_bin"

  setup_postgres
  ensure_env_file
  create_virtualenv "$py_bin"
  install_interface_deps
  print_summary
}

main "$@"
