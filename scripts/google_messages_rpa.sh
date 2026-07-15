#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

BACKEND_SERVICE="backend"
VNC_CONTAINER_PORT="5901"
LOCAL_TUNNEL_PORT="5902"

usage() {
  cat <<EOF
Uso:
  ./scripts/google_messages_rpa.sh status
  ./scripts/google_messages_rpa.sh start-pairing
  ./scripts/google_messages_rpa.sh stop
  ./scripts/google_messages_rpa.sh diagnose
  ./scripts/google_messages_rpa.sh test <telefono> [mensaje]

Comandos:
  status         Muestra procesos temporales y valida si VNC responde.
  start-pairing Limpia perfil, levanta VNC y abre Google Messages para iniciar sesión/vincular.
  stop           Cierra Chrome/VNC/fluxbox temporales y libera locks del perfil.
  diagnose       Revisa si Google Messages está vinculado o cayó en pantalla welcome/login.
  test           Envía SMS directo usando el sender real del backend.

Después de start-pairing, desde tu PC abre túnel:
  ssh -N -p 23332 -L ${LOCAL_TUNNEL_PORT}:127.0.0.1:${VNC_CONTAINER_PORT} adminrdp@184.107.165.75

Y en TigerVNC conecta a:
  127.0.0.1::${LOCAL_TUNNEL_PORT}
EOF
}

kill_temp_processes() {
  docker compose exec "$BACKEND_SERVICE" sh -lc 'python - <<PY
from pathlib import Path
import os, signal, time

targets = [
    "x11vnc",
    "fluxbox",
    "chrome",
    "chromium",
    "open_google_messages_pairing.py",
    "google_messages_qr_capture.py",
]

current_pid = os.getpid()
parent_pid = os.getppid()

for proc in Path("/proc").iterdir():
    if not proc.name.isdigit():
        continue

    pid = int(proc.name)
    if pid in {current_pid, parent_pid}:
        continue

    try:
        comm = (proc / "comm").read_text(errors="ignore").strip()
        cmd = (proc / "cmdline").read_bytes().replace(b"\x00", b" ").decode("utf-8", errors="ignore")
    except Exception:
        continue

    if comm in targets or any(target in cmd for target in targets):
        try:
            os.kill(pid, signal.SIGTERM)
            print("Killed", pid, comm, cmd[:180])
        except Exception as exc:
            print("Could not kill", pid, comm, exc)

time.sleep(2)
PY'
}

clean_profile_locks() {
  docker compose exec "$BACKEND_SERVICE" sh -lc '
rm -f \
  /app/.playwright/google_messages_profile/SingletonLock \
  /app/.playwright/google_messages_profile/SingletonSocket \
  /app/.playwright/google_messages_profile/SingletonCookie

echo "Locks limpiados."
'
}

status() {
  docker compose exec "$BACKEND_SERVICE" sh -lc 'python - <<PY
from pathlib import Path
import socket

print("Procesos temporales:")
found = False

for proc in Path("/proc").iterdir():
    if not proc.name.isdigit():
        continue

    try:
        comm = (proc / "comm").read_text(errors="ignore").strip()
        cmd = (proc / "cmdline").read_bytes().replace(b"\x00", b" ").decode("utf-8", errors="ignore")
    except Exception:
        continue

    if comm in {"x11vnc", "fluxbox", "chrome", "chromium"} or "open_google_messages_pairing.py" in cmd:
        found = True
        print(proc.name, comm, cmd[:220])

if not found:
    print("Sin procesos temporales detectados.")

print("")
try:
    s = socket.create_connection(("127.0.0.1", 5901), timeout=3)
    print("OK VNC responde:", s.recv(12))
    s.close()
except Exception as exc:
    print("VNC no responde:", repr(exc))
PY'
}

start_pairing() {
  echo "Cerrando procesos temporales..."
  kill_temp_processes || true
  clean_profile_locks

  echo "Levantando fluxbox..."
  docker compose exec -d "$BACKEND_SERVICE" sh -lc '
export DISPLAY=:99
exec fluxbox >/tmp/suite_fluxbox.log 2>&1
'

  echo "Levantando x11vnc..."
  docker compose exec -d "$BACKEND_SERVICE" sh -lc '
export DISPLAY=:99
exec x11vnc \
  -display :99 \
  -forever \
  -shared \
  -nopw \
  -noxdamage \
  -rfbversion 3.8 \
  -listen 0.0.0.0 \
  -rfbport 5901 \
  >/tmp/suite_x11vnc.log 2>&1
'

  sleep 3

  echo "Abriendo Google Messages..."
  docker compose exec -d "$BACKEND_SERVICE" sh -lc 'cat >/tmp/open_google_messages_pairing.py <<PY
from pathlib import Path
from playwright.sync_api import sync_playwright
import time

profile_dir = Path("/app/.playwright/google_messages_profile")

with sync_playwright() as pw:
    context = pw.chromium.launch_persistent_context(
        str(profile_dir),
        headless=False,
        viewport={"width": 1368, "height": 900},
        args=[
            "--no-sandbox",
            "--disable-notifications",
            "--disable-gpu",
            "--disable-dev-shm-usage",
            "--disable-setuid-sandbox",
            "--disable-blink-features=AutomationControlled",
        ],
    )

    page = context.pages[0] if context.pages else context.new_page()
    page.goto("https://messages.google.com/web/welcome", wait_until="domcontentloaded")

    while True:
        time.sleep(60)
PY

cd /app
export DISPLAY=:99
exec python /tmp/open_google_messages_pairing.py >/tmp/google_messages_pairing.log 2>&1
'

  sleep 5
  status

  cat <<EOF

Listo para vincular.

Desde tu PC abre una PowerShell nueva y deja corriendo:
  ssh -N -p 23332 -L ${LOCAL_TUNNEL_PORT}:127.0.0.1:${VNC_CONTAINER_PORT} adminrdp@184.107.165.75

En TigerVNC conecta a:
  127.0.0.1::${LOCAL_TUNNEL_PORT}

Cuando termines de iniciar sesión/vincular, ejecuta:
  ./scripts/google_messages_rpa.sh stop
  ./scripts/google_messages_rpa.sh test 6863408369
EOF
}

stop_pairing() {
  echo "Cerrando procesos temporales..."
  kill_temp_processes || true
  clean_profile_locks
  echo "Perfil libre para sender automático."
}

diagnose() {
  docker compose exec -T "$BACKEND_SERVICE" sh -lc 'cd /app && python -' <<'PY'
from playwright.sync_api import sync_playwright
import json

from app.rpa.services.google_messages_sms_sender_service import (
    MESSAGES_NEW_URL,
    resolve_config_from_env,
)

config = resolve_config_from_env()

with sync_playwright() as pw:
    context = pw.chromium.launch_persistent_context(
        str(config.profile_dir),
        headless=config.headless,
        viewport={"width": 1368, "height": 900},
        args=[
            "--no-sandbox",
            "--disable-notifications",
            "--disable-gpu",
            "--disable-dev-shm-usage",
            "--disable-setuid-sandbox",
            "--disable-blink-features=AutomationControlled",
        ],
    )

    page = context.pages[0] if context.pages else context.new_page()
    page.goto(MESSAGES_NEW_URL, wait_until="domcontentloaded", timeout=config.timeout_ms)
    page.wait_for_timeout(8000)

    body_text = ""
    try:
        body_text = page.locator("body").first.inner_text(timeout=3000)
    except Exception as exc:
        body_text = f"ERROR reading body: {type(exc).__name__}: {exc}"

    recipient = page.locator("input[data-e2e-contact-input], input[type='text']")
    loader = page.locator("#loader")

    data = {
        "current_url": page.url,
        "title": page.title(),
        "recipient_input_count": recipient.count(),
        "loader_count": loader.count(),
        "body_text_first_1200": body_text[:1200],
    }

    print(json.dumps(data, ensure_ascii=False, indent=2))
    context.close()
PY
}

test_sms() {
  local phone="${1:-}"
  shift || true
  local message="${*:-Prueba Suite Ultra: Google Messages operativo.}"

  if [[ -z "$phone" ]]; then
    echo "Falta teléfono."
    echo "Uso: ./scripts/google_messages_rpa.sh test 6863408369"
    exit 1
  fi

  echo "Liberando perfil antes de prueba..."
  stop_pairing

  TEST_PHONE="$phone" TEST_MESSAGE="$message" \
  docker compose exec -T -e TEST_PHONE -e TEST_MESSAGE "$BACKEND_SERVICE" sh -lc 'cd /app && python -' <<'PY'
import os
from app.rpa.services.google_messages_sms_sender_service import send_sms_via_google_messages

phone = os.environ["TEST_PHONE"]
message = os.environ["TEST_MESSAGE"]

print("Enviando SMS directo...")
result = send_sms_via_google_messages(phone, message)

print("OK SMS RESULT")
print(result)
PY
}

cmd="${1:-}"
shift || true

case "$cmd" in
  status)
    status
    ;;
  start-pairing)
    start_pairing
    ;;
  stop)
    stop_pairing
    ;;
  diagnose)
    diagnose
    ;;
  test)
    test_sms "$@"
    ;;
  ""|-h|--help|help)
    usage
    ;;
  *)
    echo "Comando no reconocido: $cmd"
    usage
    exit 1
    ;;
esac
