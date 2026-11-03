#!/usr/bin/env python3
"""CAP-V1: grabación reproducible de un recorrido REAL de Angular con Playwright.

Ejecutar exclusivamente contra Suite Ultra local y una BD aislada y desechable.
No escribe en producción, no altera código Angular/Flask y no almacena claves.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
from urllib.parse import urlparse
from datetime import datetime, timezone

from playwright.sync_api import sync_playwright

from scripts.training.recording_focus import install_focus_context, install_focus_page, guided_click, guided_action

ROOT = Path(__file__).resolve().parent
LOOPBACK = {"localhost", "127.0.0.1", "::1"}
EXPECTED_ACK = "BD_DE_CAPACITACION_AISLADA"


def validate_target(url: str, acknowledgement: str) -> str:
    parsed = urlparse(url)
    if (parsed.scheme != "http" or parsed.hostname not in LOOPBACK
            or parsed.username or parsed.password or parsed.path not in ("", "/")
            or parsed.query or parsed.fragment or parsed.port is None):
        raise ValueError("Solo se permite una URL HTTP local con puerto explícito; nunca producción.")
    if acknowledgement != EXPECTED_ACK:
        raise ValueError("Falta la confirmación explícita de BD de capacitación aislada.")
    return url.rstrip("/")


def validate_codes(codes: list[str]) -> None:
    if len(codes) < 3 or len(set(codes)) != len(codes) or any(not c.strip() for c in codes):
        raise ValueError("El piloto requiere al menos 3 códigos únicos de aparatos de DEMO.")


def load_storyboard(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    required = ("inicio", "ticket", "parcial", "completo", "cierre",
                "rechazo", "reversion", "historial", "fin")
    if any(not isinstance(data.get(key), str) or not data[key].strip() for key in required):
        raise ValueError("Storyboards incompletos o sin narración.")
    return data


def srt_time(seconds: float) -> str:
    milli = round(max(0, seconds) * 1000)
    hours, milli = divmod(milli, 3_600_000)
    minutes, milli = divmod(milli, 60_000)
    secs, milli = divmod(milli, 1000)
    return f"{hours:02}:{minutes:02}:{secs:02},{milli:03}"


def make_srt(scenes: list[dict], duration: float, path: Path) -> None:
    parts = []
    for i, scene in enumerate(scenes):
        start = max(0.0, float(scene["at"]))
        end = min(duration, float(scenes[i + 1]["at"]) if i + 1 < len(scenes)
                  else duration)
        # No se muestra el texto siguiente antes de iniciar su escena.
        if end <= start:
            end = start + 0.25
        parts.append(f'{i + 1}\n{srt_time(start)} --> {srt_time(end)}\n{scene["text"]}\n')
    path.write_text("\n".join(parts) + "\n", encoding="utf-8")


def command(args: list[str], cwd: Path) -> None:
    subprocess.run(args, cwd=cwd, check=True, stdout=subprocess.PIPE,
                   stderr=subprocess.PIPE, text=True)


def export_video(raw: Path, out: Path, scenes: list[dict], voice: str) -> Path:
    if not shutil.which("ffmpeg"):
        raise RuntimeError("Se necesita FFmpeg disponible en PATH.")
    srt = out / "subtitulos.srt"
    # Generar audio por escena evita desfases al variar el tiempo de interacción.
    audio_args = []
    filters = []
    if voice == "espeak":
        exe = shutil.which("espeak-ng") or shutil.which("espeak")
        if not exe:
            raise RuntimeError("Modo espeak requiere espeak-ng o espeak en PATH.")
        for i, scene in enumerate(scenes):
            wav = out / f"voz-{i:02}.wav"
            command([exe, "-v", "es", "-s", "155", "-w", str(wav), scene["text"]], out)
            audio_args.extend(["-i", str(wav)])
            delay = round(float(scene["at"]) * 1000)
            filters.append(f"[{i + 1}:a]adelay={delay}|{delay}[a{i}]")
    mp4 = out / "capacitacion.mp4"
    # Todos los -i ANTES de opciones de salida; FFmpeg no acepta -map
    # delante de un input pendiente.
    ff = ["ffmpeg", "-y", "-i", str(raw), *audio_args, "-i", str(srt)]
    if filters:
        joins = "".join(f"[a{i}]" for i in range(len(scenes)))
        graph = ";".join(filters + [f"{joins}amix=inputs={len(scenes)}:duration=longest:normalize=0[narracion]"])
        ff += ["-filter_complex", graph, "-map", "0:v:0", "-map", "[narracion]"]
    else:
        ff += ["-map", "0:v:0"]
    # MP4 con subtítulos embebidos activables + SRT independiente.
    ff += ["-map", f"{1 + len(scenes) if filters else 1}:s:0",
           "-c:v", "libx264", "-crf", "22", "-preset", "veryfast",
           "-pix_fmt", "yuv420p", "-c:s", "mov_text",
           "-metadata:s:s:0", "language=spa", "-movflags", "+faststart"]
    if filters:
        ff += ["-c:a", "aac", "-b:a", "128k"]
    ff += [str(mp4)]
    command(ff, out)
    if not mp4.is_file() or mp4.stat().st_size == 0:
        raise RuntimeError("FFmpeg no generó el MP4.")
    return mp4


def find_ticket(page, ticket_id: int, max_pages: int = 20):
    # La bandeja no dispone de búsqueda directa por ID: recorrer paginación real.
    for _ in range(max_pages):
        page.locator(".tabla-tickets tbody tr").first.wait_for(timeout=20_000)
        rows = page.locator(".tabla-tickets tbody tr")
        for index in range(rows.count()):
            row = rows.nth(index)
            if row.locator("td").first.inner_text().strip() == str(ticket_id):
                return row
        nxt = page.get_by_role("button", name="Siguiente", exact=True)
        if not nxt.count() or not nxt.is_enabled():
            break
        guided_click(page, nxt)
    raise RuntimeError(f"No se encontró el ticket DEMO #{ticket_id} en la bandeja.")


def open_receipt(page, ticket_id: int):
    row = find_ticket(page, ticket_id)
    guided_click(page, row.get_by_role("button", name=f"Gestionar recepción de tapizado del ticket {ticket_id}"))
    dlg = page.locator("mat-dialog-container").filter(has_text="Recepción de tapizado")
    dlg.wait_for()
    dlg.get_by_text("Actualizando información de aparatos").wait_for(state="hidden", timeout=20_000) if dlg.get_by_text("Actualizando información de aparatos", exact=False).count() else None
    return dlg


def ensure_progress(dialog, received: int, total: int) -> None:
    dialog.get_by_text(f"{received} de {total} recibidos").wait_for(timeout=20_000)


def batch_receive(page, dialog, codes: list[str], received: bool, reason: str = "") -> None:
    for code in codes:
        item = dialog.locator(".tapizado-avance__fila").filter(has_text=code)
        if item.count() != 1:
            raise RuntimeError(f"Código de demo ambiguo o ausente: {code}")
        check = item.get_by_role("checkbox")
        if received:
            guided_action(page, check, "check")
        else:
            guided_action(page, check, "uncheck")
            item.get_by_placeholder("Obligatorio para corregir una recepción guardada").fill(reason)
    guided_click(page, dialog.get_by_role("button", name=re.compile("Guardar cambios")))
    dialog.get_by_role("button", name=re.compile("Guardar cambios")).wait_for(state="hidden", timeout=30_000)


def login(page, url: str, username: str, password: str):
    """Autenticar fuera del formulario grabado. Solo credenciales sintéticas CI.

    El video jamás muestra campos ni tecleo de contraseñas. El usuario/rol/branch
    se valida por la respuesta real del backend; no se inventan JWT ni guards.
    """
    if username not in ("QA_COORD_CIERRE", "QA_GERENTE_CIERRE"):
        raise ValueError("CAP-V1: solamente cuentas de capacitación sintética")
    response = page.context.request.post(
        url + "/api/auth/login",
        data={"username": username, "password": password},
        timeout=20000, max_redirects=0,
    )
    if response.status != 200:
        raise RuntimeError("CAP-V1: login sintético rechazado (HTTP %s)" % response.status)
    payload = response.json()
    user = payload.get("user") or {}
    expected_role = "COMPRAS" if username == "QA_COORD_CIERRE" else "GERENTE"
    if (user.get("sucursal_id") != 990101
            or user.get("rol") != expected_role
            or user.get("username", "").upper() != username
            or not payload.get("token")):
        raise RuntimeError("CAP-V1: cuenta/rol/sucursal no corresponden a QA")
    # El primer documento no graba tecleo alguno; cambios posteriores de
    # cuenta sustituyen el estado local sin entrar a la pantalla de login.
    if page.url == "about:blank":
        page.goto(url + "/", wait_until="domcontentloaded")
    page.evaluate(
        """(auth) => {
            localStorage.removeItem('token');
            localStorage.removeItem('user');
            localStorage.setItem('token', auth.token);
            localStorage.setItem('user', JSON.stringify(auth.user));
            sessionStorage.clear();
        }""",
        {"token": payload["token"], "user": user},
    )


def switch_account(page, url: str, username: str, password: str):
    page.context.clear_cookies()
    login(page, url, username, password)
    # Angular conserva el objeto User/rol si se navega al mismo hash.
    # Recargar crea una instancia de app vinculada al nuevo localStorage.
    # El formulario de login nunca aparece con credenciales en la captura.
    page.reload(wait_until="domcontentloaded")


def ticket_page(page, url: str):
    page.goto(url + "/#/main/ver-tickets")
    page.get_by_role("heading", name="Ver Tickets").wait_for(timeout=30_000)
    install_focus_page(page)


def observe_ticket_state(page, url: str, ticket_id: int) -> dict:
    """Diagnóstico de un ticket sintético autorizado, sin exponer el JWT."""
    if not os.getenv("CAP_V1_SYNTHETIC_CI"):
        return {}
    token = page.evaluate("() => localStorage.getItem('token')")
    response = page.context.request.get(
        url + "/api/tickets/all?limit=50&offset=0",
        headers={"Authorization": "Bearer " + token},
        timeout=15000, max_redirects=0,
    )
    if response.status != 200:
        raise RuntimeError(f"CAP-V1 QA: la bandeja API respondió {response.status}")
    ticket = next((t for t in response.json().get("tickets", [])
                   if t.get("id") == ticket_id), None)
    if not ticket:
        raise RuntimeError("CAP-V1 QA: ticket sintético fuera de alcance")
    return {
        "estado": ticket.get("estado"), "estado_cierre": ticket.get("estado_cierre"),
        "username": ticket.get("username"),
        "sucursal_id_destino": ticket.get("sucursal_id_destino"),
    }


def walkthrough(page, args, story: dict):
    username, password = os.environ["CAP_ACTOR_USER"], os.environ["CAP_ACTOR_PASSWORD"]
    reviewer, reviewer_pass = os.environ["CAP_REVIEWER_USER"], os.environ["CAP_REVIEWER_PASSWORD"]
    scenes: list[dict] = []
    segments: list[dict] = []
    active_segment = None
    start = time.monotonic()

    def begin_segment(key: str, role: str) -> None:
        nonlocal active_segment
        if not args.cap_v2:
            return
        if active_segment is not None or role not in ("mantenimiento", "gerencia"):
            raise RuntimeError("CAP-V2: marcador de rol superpuesto o desconocido")
        active_segment = {
            "key": key, "role": role,
            "start": round(time.monotonic() - start, 3)
        }

    def end_segment() -> None:
        nonlocal active_segment
        if not args.cap_v2:
            return
        if active_segment is None:
            raise RuntimeError("CAP-V2: fin de sección sin inicio")
        active_segment["end"] = round(time.monotonic() - start, 3)
        if active_segment["end"] <= active_segment["start"]:
            raise RuntimeError("CAP-V2: sección sin video")
        segments.append(active_segment)
        active_segment = None

    def scene(key: str):
        scenes.append({"key": key, "text": story[key], "at": round(time.monotonic() - start, 3)})
        # V2 narra sobre acciones, sin retener una pantalla inmóvil por longitud del texto.
        # V1 se conserva sin cambios para compatibilidad con su piloto.
        if args.cap_v2:
            page.wait_for_timeout(500)
        else:
            page.wait_for_timeout(max(3500, int(len(story[key].split()) / 2.5 * 1000)))

    login(page, args.base_url, username, password)
    ticket_page(page, args.base_url)
    begin_segment("inicio", "mantenimiento")
    scene("inicio")
    end_segment()
    begin_segment("ticket", "mantenimiento")
    row = find_ticket(page, args.ticket_id)
    if "Tapizado" not in row.inner_text():
        raise RuntimeError("El ticket seleccionado no es de tapizado.")
    guided_click(page, row.get_by_role("button", name="Ver Historial"))
    page.locator("mat-dialog-container").filter(has_text=f"#{args.ticket_id}").wait_for()
    scene("ticket")
    guided_click(page, page.locator("mat-dialog-container").get_by_role("button", name="Cerrar").last)
    end_segment()
    begin_segment("parcial", "mantenimiento")
    dlg = open_receipt(page, args.ticket_id)
    ensure_progress(dlg, 0, len(args.codes))
    batch_receive(page, dlg, args.codes[:2], True)
    ensure_progress(dlg, 2, len(args.codes))
    scene("parcial")
    end_segment()
    begin_segment("completo", "mantenimiento")
    batch_receive(page, dlg, args.codes[2:], True)
    ensure_progress(dlg, len(args.codes), len(args.codes))
    scene("completo")
    end_segment()
    begin_segment("cierre", "mantenimiento")
    guided_click(page, dlg.get_by_role("button", name="Cerrar", exact=True))

    row = find_ticket(page, args.ticket_id)
    button = row.get_by_role("button", name=re.compile("Solicitar cierre|Revisar cierre"))
    button.wait_for(timeout=20_000)
    guided_click(page, button)
    finish = page.locator("mat-dialog-container").filter(has_text="Solicitud de conformidad")
    finish.get_by_role("textbox", name="Notas de revisión (obligatorias)").fill(
        "Recepción de todos los aparatos verificada en capacitación.")
    guided_click(page, finish.get_by_role("button", name="Solicitar conformidad"))
    scene("cierre")
    after_request = observe_ticket_state(page, args.base_url, args.ticket_id)
    if after_request and (after_request["estado"] != "por_validar"
                          or after_request["estado_cierre"] != "pendiente_creador"):
        raise RuntimeError(
            "CAP-V1 QA: solicitud no creó pendiente de conformidad: "
            + str(after_request)
        )
    end_segment()

    # Las autenticaciones y cambios de pantalla NO entran en ningún video por rol.
    switch_account(page, args.base_url, reviewer, reviewer_pass)
    ticket_page(page, args.base_url)
    begin_segment("rechazo", "gerencia")
    row = find_ticket(page, args.ticket_id)
    reviewer_status = observe_ticket_state(page, args.base_url, args.ticket_id)
    if reviewer_status and (reviewer_status["estado"] != "por_validar"
                            or reviewer_status["estado_cierre"] != "pendiente_creador"):
        raise RuntimeError("CAP-V1 QA: vista de revisor no está por validar: "
                           + str(reviewer_status))
    guided_click(page, row.get_by_role("button", name="Rechazar cierre"))
    page.locator(".swal2-textarea").fill("Se detectó un equipo que requiere corregir su recepción.")
    guided_click(page, page.locator(".swal2-confirm"))
    guided_click(page, page.locator("mat-dialog-container").filter(has_text="Rechazar cierre").get_by_role("button", name="Aceptar"))
    scene("rechazo")
    end_segment()

    switch_account(page, args.base_url, username, password)
    ticket_page(page, args.base_url)
    begin_segment("reversion", "mantenimiento")
    dlg = open_receipt(page, args.ticket_id)
    ensure_progress(dlg, len(args.codes), len(args.codes))
    batch_receive(page, dlg, [args.codes[-1]], False, "Corrección didáctica: equipo no listo.")
    ensure_progress(dlg, len(args.codes) - 1, len(args.codes))
    scene("reversion")
    guided_click(page, dlg.get_by_role("button", name="Cerrar", exact=True))
    row = find_ticket(page, args.ticket_id)
    # Esperar el refresco real de la bandeja antes de comprobar el bloqueo.
    row.get_by_text(
        f"Tapizado · {len(args.codes) - 1}/{len(args.codes)} recibidos"
    ).wait_for(timeout=30_000)
    # Ni cierre de mantenimiento ni cierre genérico deben estar disponibles.
    if row.get_by_role(
        "button", name=re.compile("Solicitar cierre|Revisar cierre|Finalizar|Cierre gerente")
    ).count():
        raise RuntimeError("REGRESIÓN: se ofrece cierre con recepción incompleta.")
    end_segment()
    begin_segment("historial", "mantenimiento")
    guided_click(page, row.get_by_role("button", name="Ver Historial"))
    history = page.locator("mat-dialog-container").filter(has_text="Historial de solución")
    history.get_by_text("Historial de solución").wait_for()
    scene("historial")
    end_segment()
    begin_segment("fin", "mantenimiento")
    scene("fin")
    end_segment()
    return (scenes, segments) if args.cap_v2 else scenes


def main(argv=None):
    ap = argparse.ArgumentParser(description="Capacitación Playwright real — Tapizado M1–M4")
    ap.add_argument("--base-url", default="http://127.0.0.1:4200")
    ap.add_argument("--isolated-ack", required=True)
    ap.add_argument("--ticket-id", type=int, required=True)
    ap.add_argument("--codes", nargs="+", required=True)
    ap.add_argument("--storyboard", type=Path, default=ROOT / "storyboards/tapizado_multiaparato.json")
    ap.add_argument("--output", type=Path, default=Path("artifacts/capacitacion/tapizado"))
    ap.add_argument("--voice", choices=("espeak", "none"), default="espeak")
    ap.add_argument("--cap-v2", action="store_true",
                    help="Marcar secciones por rol sin pausas narrativas; no publica nada")
    args = ap.parse_args(argv)
    args.base_url = validate_target(args.base_url, args.isolated_ack)
    if args.ticket_id <= 0:
        ap.error("ticket-id debe ser positivo")
    validate_codes(args.codes)
    story = load_storyboard(args.storyboard)
    for name in ("CAP_ACTOR_USER", "CAP_ACTOR_PASSWORD", "CAP_REVIEWER_USER", "CAP_REVIEWER_PASSWORD"):
        if not os.environ.get(name):
            ap.error(f"Falta variable de entorno {name} (no introducir contraseñas en argumentos).")
    if not shutil.which("ffmpeg"):
        ap.error("No se encontró FFmpeg.")
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=True)
    scenes = []
    segments = []
    source = out / "navegacion.webm"
    error = None
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1920, "height": 1080},
                                      record_video_dir=str(out),
                                      record_video_size={"width": 1920, "height": 1080},
                                      locale="es-MX", timezone_id="America/Tijuana")
        def guard(route):
            dest = urlparse(route.request.url)
            if dest.scheme in ("http", "https") and dest.hostname not in LOOPBACK:
                route.abort("blockedbyclient")
            else:
                route.continue_()
        context.route("**/*", guard)
        install_focus_context(context)
        page = context.new_page()
        video = page.video
        try:
            result = walkthrough(page, args, story)
            if args.cap_v2:
                scenes, segments = result
            else:
                scenes = result
        except Exception as exc:
            error = str(exc)
            page.screenshot(path=str(out / "fallo.png"))
        finally:
            context.close()
            if video:
                video.save_as(str(source))
            browser.close()
    if error:
        (out / "fallo.txt").write_text(error + "\n", encoding="utf-8")
        raise RuntimeError(f"Recorrido incompleto: {error}. Ver fallo.png; NO publicar.")
    # El video de Playwright empieza al crear la página; el último intervalo se conserva.
    duration = (segments[-1]["end"] if args.cap_v2 else
                scenes[-1]["at"] + max(3.5, len(scenes[-1]["text"].split()) / 2.5))
    make_srt(scenes, duration, out / "subtitulos.srt")
    mp4 = export_video(source, out, scenes, args.voice)
    manifest = {
        "schema": "suite-ultra-training-v1", "storyboard": args.storyboard.name,
        "ticket_id_demo": args.ticket_id, "aparatos_demo": len(args.codes),
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "entorno": "loopback-aislado-declarado", "escenas": scenes,
        "artefactos": ["navegacion.webm", "capacitacion.mp4", "subtitulos.srt"],
        "publicacion_nube": "BLOQUEADA: MP4 no admitido en extensiones actuales",
    }
    if args.cap_v2:
        manifest["cap_v2_source"] = True
        manifest["segmentos"] = segments
        manifest["artefactos"].append("navegacion.webm")
    (out / "manifiesto.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
                                          encoding="utf-8")
    print(f"CAP-V1 PASS: {mp4} ({mp4.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
