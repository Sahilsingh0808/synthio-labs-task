#!/usr/bin/env bash
# VoiceSlide deploy script.
#
# Usage:
#   ./deploy.sh              # build + restart stack, wait for healthy
#   ./deploy.sh --pull       # git pull first
#   ./deploy.sh --fresh      # no-cache rebuild
#   ./deploy.sh --logs       # tail logs after deploy
#   ./deploy.sh --stop       # stop and remove the stack
#   ./deploy.sh --status     # show current status
#   ./deploy.sh --help

set -euo pipefail

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

if [[ -t 1 ]]; then
    BLUE='\033[0;34m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'
else
    BLUE=''; GREEN=''; YELLOW=''; RED=''; NC=''
fi
log()  { printf "${BLUE}[deploy]${NC} %s\n" "$*"; }
ok()   { printf "${GREEN}[deploy] ✓${NC} %s\n" "$*"; }
warn() { printf "${YELLOW}[deploy] !${NC} %s\n" "$*"; }
err()  { printf "${RED}[deploy] ✗${NC} %s\n" "$*" >&2; }

PULL=0; FRESH=0; LOGS=0; STOP=0; STATUS_ONLY=0
while [[ $# -gt 0 ]]; do
    case "$1" in
        --pull)   PULL=1; shift ;;
        --fresh)  FRESH=1; shift ;;
        --logs)   LOGS=1; shift ;;
        --stop)   STOP=1; shift ;;
        --status) STATUS_ONLY=1; shift ;;
        -h|--help)
            cat <<'EOF'
VoiceSlide deploy script.

Usage:
  ./deploy.sh              build + (re)start stack, wait for healthy
  ./deploy.sh --pull       git pull --ff-only before deploying
  ./deploy.sh --fresh      no-cache rebuild
  ./deploy.sh --logs       tail logs after deploy
  ./deploy.sh --stop       stop and remove the stack
  ./deploy.sh --status     show current docker compose status
  ./deploy.sh --help

Expects:
  backend/.env                  Azure / OpenAI credentials (required)
  .env                          compose overrides (optional)
                                  BASIC_AUTH_USERNAME / BASIC_AUTH_PASSWORD
                                  FRONTEND_PORT / VITE_API_BASE / VITE_WS_BASE
EOF
            exit 0
            ;;
        *) err "unknown arg: $1"; exit 1 ;;
    esac
done

# Compose reads ${VAR} directly from the environment. If it's unset, it
# whines with a warning — export empty defaults so the output stays clean.
export BIND_HOST="${BIND_HOST-}"
export FRONTEND_PORT="${FRONTEND_PORT-}"
export VITE_API_BASE="${VITE_API_BASE-}"
export VITE_WS_BASE="${VITE_WS_BASE-}"
export BASIC_AUTH_USERNAME="${BASIC_AUTH_USERNAME-}"
export BASIC_AUTH_PASSWORD="${BASIC_AUTH_PASSWORD-}"
export ALLOWED_ORIGINS="${ALLOWED_ORIGINS-}"

# ─── Preflight ────────────────────────────────────────────────────────────────
log "Preflight…"
command -v docker >/dev/null 2>&1 || { err "docker not installed"; exit 1; }
docker compose version >/dev/null 2>&1 || { err "docker compose v2 required"; exit 1; }

if [[ $STATUS_ONLY -eq 1 ]]; then
    docker compose ps
    exit 0
fi

if [[ $STOP -eq 1 ]]; then
    log "Stopping stack…"
    docker compose down
    ok "Stopped."
    exit 0
fi

if [[ ! -f backend/.env ]]; then
    err "backend/.env missing."
    err "  cp backend/.env.example backend/.env  && fill in your Azure / OpenAI credentials."
    exit 1
fi

if [[ -f .env ]]; then
    ok "Found repo-root .env (compose will pick up BASIC_AUTH / FRONTEND_PORT / VITE_* overrides)."
else
    warn "No repo-root .env — using defaults (auth disabled, FRONTEND_PORT=5173)."
fi

# ─── Git pull ─────────────────────────────────────────────────────────────────
if [[ $PULL -eq 1 ]]; then
    log "git pull --ff-only…"
    git pull --ff-only
fi

# ─── Build ────────────────────────────────────────────────────────────────────
if [[ $FRESH -eq 1 ]]; then
    log "Building (--no-cache)…"
    docker compose build --no-cache
else
    log "Building…"
    docker compose build
fi

# ─── Up ───────────────────────────────────────────────────────────────────────
log "Starting stack…"
docker compose up -d

# ─── Wait for healthy ─────────────────────────────────────────────────────────
log "Waiting for healthchecks (90s timeout)…"
deadline=$(( $(date +%s) + 90 ))
printed_dot=0
while true; do
    backend_h=$(docker inspect --format '{{.State.Health.Status}}' voiceslide-backend 2>/dev/null || echo "missing")
    frontend_h=$(docker inspect --format '{{.State.Health.Status}}' voiceslide-frontend 2>/dev/null || echo "missing")
    if [[ "$backend_h" == "healthy" && "$frontend_h" == "healthy" ]]; then
        [[ $printed_dot -eq 1 ]] && echo
        ok "Both services healthy (backend=$backend_h, frontend=$frontend_h)."
        break
    fi
    if (( $(date +%s) >= deadline )); then
        [[ $printed_dot -eq 1 ]] && echo
        err "Timed out waiting for health: backend=$backend_h frontend=$frontend_h"
        docker compose logs --tail 40
        exit 1
    fi
    printf "."
    printed_dot=1
    sleep 2
done

# ─── Summary ──────────────────────────────────────────────────────────────────
echo
log "Status:"
docker compose ps
echo
FRONTEND_PORT="${FRONTEND_PORT:-5173}"
ok "Frontend: http://localhost:${FRONTEND_PORT}"
ok "Backend:  http://localhost:9001/healthz (exposed for debugging only)"
if [[ -n "${BASIC_AUTH_USERNAME:-}" ]]; then
    ok "Basic auth enabled for user: ${BASIC_AUTH_USERNAME}"
fi

if [[ $LOGS -eq 1 ]]; then
    log "Tailing logs (Ctrl+C to exit)…"
    exec docker compose logs -f --tail 20
fi
