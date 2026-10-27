#!/usr/bin/env python3
"""CAP-V1: captura de SOLO LECTURA en la interfaz real de producción.

La grabación empieza DESPUÉS del login y la validación API is_demo.
Ni el login ni su contraseña se graban. Ningún endpoint de negocio recibe
POST/PATCH/PUT/DELETE: el navegador bloquea esos métodos fail-closed.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import shutil
import time
from urllib.parse import urlparse

from playwright.sync_api import sync_playwright

from scripts.training.generate import export_video, make_srt, find_ticket

PROD_ORIGIN = "https://suiteultragym.com"
PROD_ACK = "SOLO_LECTURA_PRODUCCION_CAP_V1"
DEMO_NAME = "ULTRA DEMO"
ALLOWED_DEMO_ROLES = frozenset({"GERENTE", "USUARIO", "RECEPCIONISTA"})
CAPTION = {
    "inicio": "Esta capacitación muestra Tickets en la interfaz real de Suite Ultra, usando exclusivamente una cuenta de la sucursal ULTRA DEMO.",
    "ticket": "Consultamos un ticket de tapizado con varios aparatos vinculados. La vista conserva los indicadores de recepción reales.",
    "historial": "En el historial podemos revisar la trazabilidad del ticket sin modificar su estado ni los datos operativos.",
    "avance": "La recepción por aparato permite consultar el progreso. En esta grabación de solo lectura no se registra ninguna recepción.",
    "fin": "Concluye el recorrido de observación. La solicitud de cierre y el rechazo requieren una validación independiente antes de automatizarse en producción.",
}


def validate_production_target(url: str, ack: str, ticket_id: int) -> str:
    parsed = urlparse(url)
    if (url != PROD_ORIGIN or parsed.scheme != "https"
            or parsed.netloc != "suiteultragym.com"
            or ack != PROD_ACK or ticket_id <= 0):
        raise ValueError("CAP-V1 producción: solo URL oficial, confirmación READ-ONLY e ID positivo.")
    return url


def request_allowed(url: str, method: str, *, login_phase: bool) -> bool:
    parsed = urlparse(url)
    if parsed.scheme in {"data", "blob"}:
        return True
    if parsed.scheme != "https" or parsed.netloc != "suiteultragym.com":
        return False
    method = method.upper()
    if method in {"GET", "HEAD", "OPTIONS"}:
        return True
    return bool(
        login_phase
        and method == "POST"
        and parsed.path == "/api/auth/login"
        and not parsed.query
    )


def demo_preflight(user: dict, branches: list, tickets: list, ticket_id: int) -> dict:
    if not isinstance(user, dict) or not isinstance(branches, list) or not isinstance(tickets, list):
        raise ValueError("Preflight: datos incompletos de API.")
    role = str(user.get("rol") or "").upper()
    if role not in ALLOWED_DEMO_ROLES:
        raise ValueError("Preflight: rol no autorizado para captura de producción.")
    branch_id = user.get("sucursal_id")
    possible = [
        item for item in branches
        if isinstance(item, dict)
        and item.get("sucursal_id") == branch_id
        and item.get("sucursal") == DEMO_NAME
        and item.get("is_demo") is True
    ]
    if len(possible) != 1:
        raise ValueError("Preflight: la cuenta no pertenece a ULTRA DEMO is_demo=true.")
    branch = possible[0]
    matches = [t for t in tickets if isinstance(t, dict) and t.get("id") == ticket_id]
    if len(matches) != 1:
        raise ValueError("Preflight: ticket no encontrado o duplicado en alcance del usuario.")
    ticket = matches[0]
    if (ticket.get("sucursal_id_destino") != branch_id
            or ticket.get("tipo_trabajo") != "TAPIZADO"
            or not isinstance(ticket.get("aparatos"), list)
            or len(ticket["aparatos"]) < 3):
        raise ValueError("Preflight: ticket no es Tapizado multiaparato en ULTRA DEMO.")
    # Usuario DEMO de scope estricto, sin visibilidad ajena en la primera muestra.
    if any(t.get("sucursal_id_destino") != branch_id for t in tickets):
        raise ValueError("Preflight: la cuenta ve tickets de otras sucursales.")
    return {"branch_id": branch_id, "ticket_id": ticket_id, "aparatos": len(ticket["aparatos"])}


def http_guard(*, login_phase: bool):
    def handler(route):
        request = route.request
        if request_allowed(request.url, request.method, login_phase=login_phase):
            route.continue_()
        else:
            route.abort("blockedbyclient")
    return handler


def retrieve_json(context, url: str, token: str):
    response = context.request.get(
        url, headers={"Authorization": "Bearer " + token},
        timeout=15000,
    )
    if response.status != 200:
        raise RuntimeError("Preflight: lectura API denegada (HTTP " + str(response.status) + ").")
    return response.json()


def locate_demo_ticket(context, token: str, ticket_id: int) -> list:
    # GET paginado; jamás solicitar todo el catálogo de Tickets de una vez.
    seen = []
    for offset in range(0, 1000, 50):
        payload = retrieve_json(
            context, PROD_ORIGIN + f"/api/tickets/all?limit=50&offset={offset}",
            token,
        )
        batch = payload.get("tickets")
        if not isinstance(batch, list):
            raise RuntimeError("Preflight: formato de bandeja inesperado.")
        seen.extend(batch)
        if any(ticket.get("id") == ticket_id for ticket in batch):
            return seen
        if len(batch) < 50:
            break
    raise ValueError("El ticket DEMO no figura entre los primeros 1000 visibles.")


def capture(args) -> None:
    out = args.output.resolve()
    if not shutil.which("ffmpeg"):
        raise RuntimeError("FFmpeg es obligatorio.")
    if not os.environ.get("CAP_PROD_DEMO_USER") or not os.environ.get("CAP_PROD_DEMO_PASSWORD"):
        raise ValueError("Faltan GitHub Secrets de la cuenta DEMO.")
    validate_production_target(args.base_url, args.readonly_ack, args.ticket_id)

    out.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        # Primera sesión sin grabación: NO incluir formulario ni credenciales.
        auth_ctx = browser.new_context(
            locale="es-MX", timezone_id="America/Tijuana",
            service_workers="block",
        )
        auth_ctx.route("**/*", http_guard(login_phase=True))
        login_page = auth_ctx.new_page()
        login_page.goto(PROD_ORIGIN + "/#/login", wait_until="domcontentloaded")
        login_page.locator("#usuario-login").fill(os.environ["CAP_PROD_DEMO_USER"])
        login_page.locator("#password-login").fill(os.environ["CAP_PROD_DEMO_PASSWORD"])
        login_page.get_by_role("button", name="Iniciar sesión").click()
        login_page.wait_for_url(re.compile(r"/#/((?!login).)+"), timeout=30000)

        state = auth_ctx.storage_state()  # solo RAM, nunca escribir JSON con JWT
        auth_info = login_page.evaluate(
            """() => ({
                user: JSON.parse(localStorage.getItem('user') || 'null'),
                hasToken: !!localStorage.getItem('token'),
            })"""
        )
        if not auth_info.get("hasToken"):
            raise RuntimeError("Autenticación sin JWT persistido.")

        # El token solo vive en memoria de este proceso y en la sesión Playwright.
        token = login_page.evaluate("() => localStorage.getItem('token')")
        branches = retrieve_json(
            auth_ctx, PROD_ORIGIN + "/api/sucursales/listar?audience=operational", token,
        )
        tickets = locate_demo_ticket(auth_ctx, token, args.ticket_id)
        verified = demo_preflight(auth_info.get("user"), branches, tickets, args.ticket_id)
        auth_ctx.close()

        # Segunda sesión GRABADA: ya autenticada y con API estrictamente GET/HEAD/OPTIONS.
        ctx = browser.new_context(
            storage_state=state,
            viewport={"width": 1920, "height": 1080},
            record_video_dir=str(out),
            record_video_size={"width": 1920, "height": 1080},
            locale="es-MX",
            timezone_id="America/Tijuana",
            service_workers="block",
        )
        ctx.route("**/*", http_guard(login_phase=False))
        page = ctx.new_page()
        video = page.video
        scenes = []
        start = time.monotonic()

        def scene(key: str):
            scenes.append({
                "key": key,
                "at": round(time.monotonic() - start, 3),
                "text": CAPTION[key],
            })
            page.wait_for_timeout(4500)

        try:
            page.goto(PROD_ORIGIN + "/#/main/ver-tickets", wait_until="domcontentloaded")
            page.get_by_role("heading", name="Ver Tickets").wait_for(timeout=30000)
            scene("inicio")
            row = find_ticket(page, args.ticket_id)
            if DEMO_NAME not in row.inner_text().upper() or "Tapizado" not in row.inner_text():
                raise ValueError("La bandeja no muestra ULTRA DEMO y Tapizado.")
            scene("ticket")

            row.get_by_role("button", name="Ver Historial").click()
            history = page.locator("mat-dialog-container").filter(has_text="Historial de solución")
            history.wait_for(timeout=15000)
            scene("historial")
            history.get_by_role("button", name="Cerrar").click()

            row = find_ticket(page, args.ticket_id)
            receipt_button = row.get_by_role(
                "button", name=f"Gestionar recepción de tapizado del ticket {args.ticket_id}",
            )
            if receipt_button.count():
                receipt_button.click()
                dialog = page.locator("mat-dialog-container").filter(has_text="Recepción de tapizado")
                dialog.wait_for(timeout=15000)
                dialog.get_by_text(
                    f"{sum(bool(x.get('recibido')) for x in next(t for t in tickets if t['id'] == args.ticket_id)['aparatos'])} de {verified['aparatos']} recibidos"
                ).wait_for(timeout=20000)
                scene("avance")
                dialog.get_by_role("button", name="Cerrar", exact=True).click()
            else:
                # Usuario sin permiso de escritura: una cuenta lectora es válida.
                # No forzar el modal ni ampliar permisos para capturar.
                scene("avance")
            scene("fin")
        finally:
            ctx.close()
            if video:
                video.save_as(str(out / "navegacion.webm"))
            browser.close()

    duration = scenes[-1]["at"] + 5.0
    make_srt(scenes, duration, out / "subtitulos.srt")
    mp4 = export_video(out / "navegacion.webm", out, scenes, args.voice)
    manifest = {
        "schema": "suite-ultra-training-prod-readonly-v1",
        "mode": "READ_ONLY",
        "environment": PROD_ORIGIN,
        "demo_branch_id": verified["branch_id"],
        "demo_ticket_id": verified["ticket_id"],
        "aparatos": verified["aparatos"],
        "recorded_utc": datetime.now(timezone.utc).isoformat(),
        "scenes": [s["key"] for s in scenes],
        "business_writes": "BLOCKED_BY_PLAYWRIGHT",
        "artifacts": ["capacitacion.mp4", "subtitulos.srt"],
    }
    (out / "manifiesto.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8",
    )
    # En Actions NO imprimir URLs con token, información de otras sucursales ni sesión.
    print(f"CAP-V1 PROD READONLY PASS: {mp4.name} ({mp4.stat().st_size} bytes)")


def main(argv=None):
    parser = argparse.ArgumentParser(description="Solo lectura CAP-V1 prod DEMO")
    parser.add_argument("--base-url", default=PROD_ORIGIN)
    parser.add_argument("--readonly-ack", required=True)
    parser.add_argument("--ticket-id", type=int, required=True)
    parser.add_argument("--output", type=Path, default=Path("artifacts/capacitacion/prod-readonly"))
    parser.add_argument("--voice", choices=("espeak", "none"), default="espeak")
    args = parser.parse_args(argv)
    capture(args)


if __name__ == "__main__":
    main()
