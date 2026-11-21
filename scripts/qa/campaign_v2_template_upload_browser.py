#!/usr/bin/env python3
"""Loopback-only UX check for the iVentas template upload dialog."""

import argparse
import base64
import json
from email import policy
from email.parser import BytesParser
from pathlib import Path
from urllib.parse import urlparse

from playwright.sync_api import expect, sync_playwright


TARGETS = [
    {"sucursal_id": 1, "sucursal_canon": "VILLAS_DEL_REY", "provider_channel_id": "demo-1"},
    {"sucursal_id": 2, "sucursal_canon": "VILLA_VERDE", "provider_channel_id": "demo-2"},
    {"sucursal_id": 3, "sucursal_canon": "TEC_MXL", "provider_channel_id": "demo-3"},
]
UPLOAD_PATH = "/api/marketing/campaigns-v2/dispatch/template-uploads"
PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jJ0sAAAAASUVORK5CYII="
)


def read_payload(request):
    content_type = request.headers["content-type"].encode("ascii")
    payload = BytesParser(policy=policy.default).parsebytes(
        b"Content-Type: " + content_type + b"\r\n\r\n" + request.post_data_buffer
    )
    parts = {part.get_param("name", header="content-disposition"): part for part in payload.iter_parts()}
    image = parts["image"]
    assert image.get_filename() == "piloto.png"
    assert image.get_payload(decode=True) == PNG
    return json.loads(parts["template"].get_payload(decode=True))


def run(base, screenshots=None):
    parsed_base = urlparse(base)
    if parsed_base.scheme != "http" or parsed_base.hostname not in {"localhost", "127.0.0.1"}:
        raise ValueError("This browser check requires a loopback frontend.")

    uploads = []
    requests = []
    if screenshots:
        screenshots.mkdir(parents=True, exist_ok=True)

    def api_stub(route):
        request = route.request
        path = urlparse(request.url).path
        if path.endswith("/campaigns-v2/options") and request.method == "GET":
            return route.fulfill(json={
                "sources": ["EXPIRED_MEMBERS"], "selectable_audience_families": [],
                "non_selectable_classifications": [], "purposes": ["UNCLASSIFIED"],
                "tariff_categories": [],
                "scope": {"is_global": True, "can_manage_dispatch_config": True, "allowed_sucursal_keys": None},
            })
        if path == UPLOAD_PATH:
            if request.method == "GET":
                return route.fulfill(json={"enabled": True, "targets": TARGETS, "rows": uploads})
            if request.method == "POST":
                payload = read_payload(request)
                requests.append(payload)
                row = {
                    "id": 801, "requested_by_user_id": 47, "created_at": "2026-11-20T18:00:00Z",
                    "name": payload["name"], "category": payload["category"], "status": "QUEUED",
                    "branches": [{**branch, "status": "QUEUED"} for branch in TARGETS
                                 if branch["sucursal_id"] in payload["branch_ids"]],
                }
                uploads.append(row)
                return route.fulfill(status=201, json=row)
        return route.fulfill(status=404, json={"error": "synthetic-not-available"})

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        context = browser.new_context(viewport={"width": 1280, "height": 900})
        context.add_init_script(script="""(() => {
            const payload = btoa(JSON.stringify({sub: '47', exp: 4102444800})).replace(/=/g, '');
            localStorage.setItem('token', 'eyJhbGciOiJIUzI1NiJ9.' + payload + '.synthetic');
            localStorage.setItem('user', JSON.stringify({id: 47, username: 'SYNTHETIC',
              rol: 'MARKETING', sucursal_id: 1}));
        })();""")
        context.route("**/api/**", api_stub)
        page = context.new_page()
        page.goto(base.rstrip("/") + "/#/marketing/campaigns-v2", wait_until="domcontentloaded")

        page.get_by_role("button", name="Abrir herramientas de campañas").click(timeout=25000)
        page.get_by_role("menuitem", name="Cargar plantillas en iVentas").click()
        dialog = page.get_by_role("dialog")
        name = dialog.get_by_label("Nombre de la plantilla")
        expect(name).to_be_in_viewport()
        name.fill("piloto_ux")
        dialog.get_by_label("Categoría").select_option("UTILITY")
        message = dialog.get_by_label("Mensaje", exact=True)
        message.fill("Hola Ana, recibimos tu solicitud.")
        message.evaluate("(el) => el.setSelectionRange(5, 8)")
        dialog.get_by_role("button", name="Crear campo").click()
        expect(dialog.get_by_text("1 · Ana", exact=True)).to_be_visible()
        message.fill("Aviso: Hola Ana, recibimos tu solicitud.")
        expect(dialog.get_by_text("1 · Ana", exact=True)).to_be_visible()

        search = dialog.get_by_role("searchbox", name="Buscar sucursal")
        search.fill("villas")
        expect(dialog.get_by_text("VILLAS DEL REY", exact=True)).to_be_visible()
        expect(dialog.get_by_text("VILLA VERDE", exact=True)).to_have_count(0)
        dialog.get_by_text("Seleccionar resultados", exact=True).click()
        search.fill("verde")
        dialog.get_by_role("checkbox", name="VILLA VERDE", exact=True).check()
        expect(dialog.get_by_text("2 de 3 sucursales seleccionadas")).to_be_visible()
        search.clear()
        expect(dialog.get_by_role("checkbox", name="VILLAS DEL REY", exact=True)).to_be_checked()
        expect(dialog.get_by_role("checkbox", name="TEC MXL", exact=True)).not_to_be_checked()
        if screenshots:
            dialog.screenshot(path=screenshots / "desktop.png")

        page.set_viewport_size({"width": 390, "height": 740})
        execute = dialog.get_by_role("button", name="Ejecutar carga")
        expect(execute).to_be_in_viewport()
        if screenshots:
            dialog.screenshot(path=screenshots / "mobile.png")
        dialog.get_by_text("Imagen y botones", exact=False).click()
        file_input = dialog.locator('input[type="file"]')
        file_input.set_input_files({"name": "invalido.gif", "mimeType": "image/gif", "buffer": b"GIF"})
        expect(dialog.get_by_role("alert")).to_have_text("Elige una imagen PNG o JPEG de hasta 5 MB.")
        expect(execute).to_be_disabled()
        file_input.set_input_files({"name": "piloto.png", "mimeType": "image/png", "buffer": PNG})
        expect(dialog.get_by_text("piloto.png", exact=True)).to_be_visible()
        dialog.get_by_role("button", name="Agregar botón").click()
        expect(execute).to_be_disabled()
        dialog.get_by_label("Texto del botón 1").fill("Ver más")
        expect(execute).to_be_in_viewport()
        execute.click()
        expect(dialog.get_by_role("status")).to_have_text("Carga #801 registrada.")
        expect(dialog.get_by_text("piloto_ux", exact=True)).to_be_visible()
        expect(dialog.get_by_text("VILLAS DEL REY", exact=True)).to_be_visible()
        expect(dialog.get_by_text("VILLA VERDE", exact=True)).to_be_visible()
        expect(dialog.get_by_text("TEC MXL", exact=True)).to_have_count(0)
        assert requests == [{
            "name": "piloto_ux", "category": "UTILITY", "branch_ids": [1, 2],
            "message": "Aviso: Hola Ana, recibimos tu solicitud.",
            "fields": [{"start": 12, "end": 15}], "buttons": ["Ver más"],
        }], requests
        print("TEMPLATE_UPLOAD_BROWSER_PASS: labels, fields, branches, image, button, mobile footer and history")
        context.close()
        browser.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--screenshots", type=Path)
    options = parser.parse_args()
    run(options.base_url, options.screenshots)
