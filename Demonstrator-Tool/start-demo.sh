#!/usr/bin/env bash
set -Eeuo pipefail

MODEL_ALLOWLIST_FILE=""
TASK_RETENTION_MINUTES=0
VISIBLE_BROWSER=0
BACKEND_URL="http://127.0.0.1:8000"
FRONTEND_URL="http://127.0.0.1:5173"

usage() {
  cat <<'EOF'
Usage: ./start-demo.sh [options]

Options:
  --model-allowlist-file FILE  JSON model allowlist (default: demo-models.json)
  --task-retention-minutes N   Delete non-archived terminal tasks after N minutes
  --visible-browser            Use a visible automation browser instead of streaming
  -h, --help                   Show this help
EOF
}

while (($# > 0)); do
  case "$1" in
    --model-allowlist-file)
      [[ $# -ge 2 ]] || { echo "Missing value for --model-allowlist-file" >&2; exit 2; }
      MODEL_ALLOWLIST_FILE="$2"
      shift 2
      ;;
    --task-retention-minutes)
      [[ $# -ge 2 ]] || { echo "Missing value for --task-retention-minutes" >&2; exit 2; }
      TASK_RETENTION_MINUTES="$2"
      shift 2
      ;;
    --visible-browser)
      VISIBLE_BROWSER=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND="$ROOT/backend"
FRONTEND="$ROOT/frontend"

[[ -n "$MODEL_ALLOWLIST_FILE" ]] || MODEL_ALLOWLIST_FILE="$ROOT/demo-models.json"
[[ "$MODEL_ALLOWLIST_FILE" = /* ]] || MODEL_ALLOWLIST_FILE="$ROOT/$MODEL_ALLOWLIST_FILE"
[[ -f "$MODEL_ALLOWLIST_FILE" ]] || {
  echo "Model allowlist file not found: $MODEL_ALLOWLIST_FILE" >&2
  exit 1
}

[[ "$TASK_RETENTION_MINUTES" =~ ^[0-9]+$ ]] || {
  echo "Task retention must be a non-negative integer." >&2
  exit 2
}

export DEMO_ALLOWED_MODELS_FILE="$(realpath "$MODEL_ALLOWLIST_FILE")"
export DEMO_SAFETY_GUARD="1"
export DEMO_TASK_RETENTION_SECONDS="$((TASK_RETENTION_MINUTES * 60))"
if [[ "${DEMO_CONTAINER:-}" == "1" ]]; then
  if ((VISIBLE_BROWSER)); then
    echo "--visible-browser is not supported inside the container." >&2
    exit 2
  fi
  export DEMO_BROWSER_HEADLESS=1
  export DEMO_BROWSER_STREAMING=1
  export VITE_BROWSER_STREAMING=true
elif ((VISIBLE_BROWSER)); then
  export DEMO_BROWSER_HEADLESS=0
  export DEMO_BROWSER_STREAMING=0
  export VITE_BROWSER_STREAMING=false
else
  export DEMO_BROWSER_HEADLESS=1
  export DEMO_BROWSER_STREAMING=1
  export VITE_BROWSER_STREAMING=true
fi

sync_example_tasks() {
  local seed_dir="${TASK_EXAMPLES_DIR:-/app/task-examples}"
  local destination_dir="$BACKEND/tasks"
  local example_records=("$seed_dir"/example-*.json)

  if [[ ! -d "$seed_dir" || ${#example_records[@]} -eq 0 ]]; then
    echo "No repository example tasks found in $seed_dir." >&2
    return 1
  fi

  mkdir -p "$destination_dir"
  for example_record in "${example_records[@]}"; do
    local example_name="${example_record##*/}"
    example_name="${example_name%.json}"
    local destination_assets="$destination_dir/$example_name"
    local staged_assets="$destination_dir/.${example_name}.sync.$$"

    cp "$example_record" "$destination_dir/$example_name.json"
    rm -rf -- "$staged_assets"
    if [[ -d "$seed_dir/$example_name" ]]; then
      mkdir -p "$staged_assets"
      cp -a "$seed_dir/$example_name/." "$staged_assets/"
    fi
    rm -rf -- "$destination_assets"
    if [[ -d "$staged_assets" ]]; then
      mv "$staged_assets" "$destination_assets"
    fi
  done

  echo "Synchronized ${#example_records[@]} repository example task(s) into $destination_dir."
}

if [[ "${DEMO_CONTAINER:-}" == "1" ]]; then
  sync_example_tasks
fi

backend_pid=""
frontend_pid=""

cleanup() {
  local status=$?
  trap - EXIT INT TERM
  for pid in "$frontend_pid" "$backend_pid"; do
    if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
      kill "$pid" 2>/dev/null || true
      wait "$pid" 2>/dev/null || true
    fi
  done
  exit "$status"
}
trap cleanup EXIT INT TERM

wait_for_url() {
  local name="$1"
  local url="$2"
  local timeout="${3:-90}"
  local deadline=$((SECONDS + timeout))
  until curl --silent --show-error --max-time 2 --fail "$url" >/dev/null 2>&1; do
    if ((SECONDS >= deadline)); then
      echo "Timed out waiting for $name at $url." >&2
      exit 1
    fi
    sleep 0.5
  done
}

echo "Starting backend..."
(
  cd "$BACKEND"
  exec uv run uvicorn main:app --host 0.0.0.0 --port 8000
) &
backend_pid=$!

if [[ "${DEMO_CONTAINER:-}" == "1" ]]; then
  # The container serves the pre-built frontend (frontend/dist) from the
  # backend itself, so there is no separate frontend process.
  wait_for_url "backend" "$BACKEND_URL/api/health"
  wait_for_url "frontend" "$BACKEND_URL/"
else
  echo "Starting frontend..."
  (
    cd "$FRONTEND"
    exec npm run dev -- --host 0.0.0.0 --port 5173 --strictPort
  ) &
  frontend_pid=$!

  wait_for_url "backend" "$BACKEND_URL/api/health"
  wait_for_url "frontend" "$FRONTEND_URL"
fi

if [[ "${DEMO_CONTAINER:-}" == "1" ]]; then
  export DEMO_BROWSER_WIDTH="${DEMO_BROWSER_WIDTH:-1280}"
  export DEMO_BROWSER_HEIGHT="${DEMO_BROWSER_HEIGHT:-720}"
  export DEMO_BROWSER_TOP=0
else
  readarray -t SCREEN_SIZE < <(xrandr --current 2>/dev/null | awk '/ connected primary| connected / {print $3; exit}' | cut -d+ -f1 | tr 'x' '\n')
  SCREEN_WIDTH="${SCREEN_SIZE[0]:-1920}"
  SCREEN_HEIGHT="${SCREEN_SIZE[1]:-1080}"
  HALF_WIDTH=$((SCREEN_WIDTH / 2))
  export DEMO_BROWSER_WIDTH="$HALF_WIDTH"
  export DEMO_BROWSER_HEIGHT="$SCREEN_HEIGHT"
  if ((VISIBLE_BROWSER)); then
    export DEMO_BROWSER_LEFT="$HALF_WIDTH"
    export DEMO_BROWSER_TOP=0
  else
    export DEMO_BROWSER_LEFT=0
    export DEMO_BROWSER_TOP=0
  fi
fi

BROWSER=""
if [[ "${DEMO_CONTAINER:-}" != "1" ]]; then
  for candidate in google-chrome google-chrome-stable chromium chromium-browser microsoft-edge; do
    if command -v "$candidate" >/dev/null 2>&1; then
      BROWSER="$(command -v "$candidate")"
      break
    fi
  done

  if [[ -n "$BROWSER" ]]; then
    WINDOW_WIDTH="$SCREEN_WIDTH"
    if ((VISIBLE_BROWSER)); then
      WINDOW_WIDTH="$HALF_WIDTH"
    fi
    "$BROWSER" \
      --new-window \
      "--app=$FRONTEND_URL" \
      "--window-position=0,0" \
      "--window-size=${WINDOW_WIDTH},${SCREEN_HEIGHT}" >/dev/null 2>&1 &
  else
    echo "Warning: no supported Chromium browser found; open $FRONTEND_URL manually." >&2
  fi
fi

echo
echo "Demo is ready:"
if [[ "${DEMO_CONTAINER:-}" == "1" ]]; then
  echo "  Frontend + API: http://localhost:8000"
else
  echo "  Frontend: $FRONTEND_URL (left half when supported by the browser)"
  echo "  Backend:  $BACKEND_URL"
fi
echo "  Models:   $MODEL_ALLOWLIST_FILE"
if ((VISIBLE_BROWSER)); then
  echo "  Browser mode: visible split-screen"
else
  echo "  Browser mode: headless live stream"
fi
if ((TASK_RETENTION_MINUTES > 0)); then
  echo "  Task retention: $TASK_RETENTION_MINUTES minute(s) for non-archived terminal tasks"
else
  echo "  Task retention: disabled"
fi
if ((VISIBLE_BROWSER)); then
  echo "  Automation browser: right half when the first task starts"
else
  echo "  Browser preview: right pane of the frontend"
fi
echo
echo "Press Ctrl+C to stop the demo."

while true; do
  if ! kill -0 "$backend_pid" 2>/dev/null \
    || { [[ -n "$frontend_pid" ]] && ! kill -0 "$frontend_pid" 2>/dev/null; }; then
    echo "A demo process exited. Check the output above for details." >&2
    exit 1
  fi
  sleep 2
done
