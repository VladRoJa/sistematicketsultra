"""Queue missing Papalote Costa reactivation templates using existing audited uploads.

The source messages are an operator-provided editorial document captured in
backend/data/marketing/papalote_regresa_20261123.json. This command does not
send WhatsApps, link Suite templates, or bypass the existing approval process.

Preview is default. --apply queues only templates whose name placeholder is
unambiguous. Two no-placeholder variants require separate confirmation.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path

from playwright.sync_api import sync_playwright
from sqlalchemy.orm import defer

from app import create_app
from app.extensions import db
from app.integrations.iventas.template_browser import read_template_inventory
from app.models.iventas_template_upload import IventasTemplateUploadORM as Upload
from app.services.marketing_campaign_v2_dispatch_config_service import list_channel_bindings
from app.services.marketing_campaign_v2_template_credentials_service import (
    load_iventas_template_credentials,
)
from app.services.marketing_campaign_v2_template_upload_service import (
    create_upload, template_upload_enabled, validate_template,
)
from scripts.marketing.link_costa_iventas_templates import _verify_actor, expected_names

BRANCH = "PAPALOTE_TJ"
DATA = Path(__file__).resolve().parents[2] / "data/marketing/papalote_regresa_20261123.json"
EXPECTED = frozenset(expected_names(BRANCH))
NAME_TOKEN = "[Nombre]"
FIELD_REVIEW = frozenset({"2regresa_299_n3", "7regresa_399_n2"})


@dataclass(frozen=True)
class QueuePlanRow:
    name: str
    status: str
    reason: str = ""


def field_offsets(message: str) -> list[dict[str, int]]:
    """Use JS/Playwright UTF-16 offsets, not Python code-point indices."""
    start = message.find(NAME_TOKEN)
    if start < 0:
        return []
    if message.find(NAME_TOKEN, start + len(NAME_TOKEN)) >= 0:
        raise ValueError("Solo se admite un campo [Nombre] por plantilla.")
    return [{
        "start": len(message[:start].encode("utf-16-le")) // 2,
        "end": len(message[:start + len(NAME_TOKEN)].encode("utf-16-le")) // 2,
    }]


def source_templates(path: Path = DATA) -> dict[str, dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    records = data["templates"]
    if len(records) != 24:
        raise ValueError("El documento de Papalote no contiene exactamente 24 plantillas.")
    names = [record["name"] for record in records]
    if len(set(names)) != 24 or set(names) != EXPECTED:
        raise ValueError("Los nombres no coinciden con las 24 plantillas de Papalote.")
    templates: dict[str, dict] = {}
    for record in records:
        name, message = record["name"], record["body"]
        if not isinstance(message, str) or not message.strip():
            raise ValueError(f"{name}: texto vacío.")
        count = message.count(NAME_TOKEN)
        if count not in (0, 1) or count != record["placeholder_count"]:
            raise ValueError(f"{name}: cantidad de variables inconsistente.")
        if bool(record["needs_field_review"]) != (name in FIELD_REVIEW):
            raise ValueError(f"{name}: revisar el contrato de campos personalizados.")
        if bool(count) == (name in FIELD_REVIEW):
            raise ValueError(f"{name}: variable [Nombre] inesperada para este contrato.")
        templates[name] = validate_template({
            "name": name, "message": message, "category": "MARKETING",
            "fields": field_offsets(message), "buttons": [],
        })
    return templates


def _papalote_binding() -> dict:
    rows = [
        row for row in list_channel_bindings(active_only=True, session=db.session)
        if row["sucursal_canon"] == BRANCH and row["is_active"] and row["is_default"]
    ]
    if len(rows) != 1:
        raise ValueError("Papalote no tiene un canal activo predeterminado único.")
    return rows[0]


def _prior_names(branch_id: int, names: frozenset[str]) -> set[str]:
    rows = db.session.query(Upload).options(defer(Upload.image)).filter(
        Upload.template["name"].as_string().in_(names)
    ).all()
    return {
        row.template["name"]
        for row in rows
        if any(int(branch["sucursal_id"]) == branch_id for branch in row.branches)
    }


def plan_queue(*, templates: dict[str, dict], provider_inventory: tuple,
               prior_names: set[str]) -> list[QueuePlanRow]:
    observed = {record.template_name.casefold() for record in provider_inventory}
    result = []
    for name in sorted(templates):
        if name in prior_names:
            result.append(QueuePlanRow(name, "PREVIOUS_UPLOAD", "Ya hay historial de carga para esta sucursal."))
        elif name in observed:
            result.append(QueuePlanRow(name, "PROVIDER_EXISTS", "El nombre ya existe en esta cuenta iVentas."))
        elif name in FIELD_REVIEW:
            result.append(QueuePlanRow(name, "VERIFY_FIELDS", "El texto no incluye [Nombre]; confirmar si es simple."))
        else:
            result.append(QueuePlanRow(name, "READY"))
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Cola controlada de plantillas Costa solo para Papalote")
    parser.add_argument("--apply", action="store_true", help="Guardar las filas READY en la cola auditada")
    parser.add_argument("--actor-id", type=int, help="Usuario autorizado de Suite que ordena la carga")
    parser.add_argument("--confirm", help="Confirmación textual")
    args = parser.parse_args()
    if args.apply and (not args.actor_id or args.confirm != "CARGAR_PAPALOTE"):
        parser.error("--apply necesita --actor-id y --confirm CARGAR_PAPALOTE")

    templates = source_templates()
    with create_app().app_context():
        if args.apply:
            _verify_actor(args.actor_id)
            if not template_upload_enabled():
                raise ValueError("El worker de cargas de iVentas no está habilitado; no se encolará nada.")
        binding = _papalote_binding()
        branch_id = binding["sucursal_id"]
        logins = load_iventas_template_credentials(session=db.session)
        if branch_id not in logins:
            raise ValueError("Papalote no tiene un acceso configurado en iVentas.")
        prior = _prior_names(branch_id, frozenset(templates))
        db.session.remove()

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            try:
                inventory = read_template_inventory(browser, logins[branch_id])
            finally:
                browser.close()
        if not any(record.channel_id == binding["provider_channel_id"] for record in inventory):
            raise ValueError("La cuenta de Papalote no devolvió su canal emisor configurado.")
        plan = plan_queue(templates=templates, provider_inventory=inventory, prior_names=prior)
        for row in plan:
            print(f"{row.name}: {row.status}" + (f" | {row.reason}" if row.reason else ""))
        counts = {status: sum(row.status == status for row in plan)
                  for status in ("READY", "VERIFY_FIELDS", "PREVIOUS_UPLOAD", "PROVIDER_EXISTS")}
        print(f"Resumen: {counts}. Canal único: {BRANCH}.")
        if not args.apply:
            print("VISTA PREVIA: no se encoló ni creó ninguna plantilla.")
            return

        enqueued = 0
        for row in plan:
            if row.status != "READY":
                continue
            # Recheck local history immediately before each committed queue row.
            if row.name in _prior_names(branch_id, frozenset({row.name})):
                print(f"{row.name}: omitida (otra carga ya existe).")
                continue
            created = create_upload(
                {**templates[row.name], "branch_ids": [branch_id]},
                None, actor_id=args.actor_id, session=db.session,
            )
            enqueued += 1
            print(f"{row.name}: QUEUED (id={created.id})", flush=True)
        print(f"Encoladas: {enqueued}. El worker procesará cada carga; revisar resultados y aprobación.")
        print("No se enviaron WhatsApps ni se alteró el catálogo de Suite.")


if __name__ == "__main__":
    main()
