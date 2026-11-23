"""One-shot, approval-checked bulk catalog link for Costa reactivation templates.

No iVentas creations, campaign creation, messaging, or scheduler side effects.
Preview by default; --apply is an explicit, authorized operator action.
Run inside the existing iventas-template-upload-worker image, which already
mounts the protected per-branch credentials workbook.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone

from playwright.sync_api import sync_playwright

from app import create_app
from app.extensions import db
from app.integrations.iventas.template_browser import read_template_inventory
from app.models.user_model import UserORM
from app.services.marketing_access import resolve_marketing_access
from app.services.marketing_campaign_v2_dispatch_config_service import (
    list_channel_bindings, list_templates, save_template,
)
from app.services.marketing_campaign_v2_template_credentials_service import (
    load_iventas_template_credentials,
)

COSTA = (
    "PASEO_2000", "CARROUSEL_TJ", "PAPALOTE_TJ", "SANTA_FE",
    "MISION_ENS", "PABELLON_RTO", "LOMA_BONITA",
)
REGULAR_FAMILIES = ("299_n3", "399_n2")
OTHER_COAST_FAMILY = "499_n1"
LOMA_FAMILY = "449_lb"
# The user-supplied message text does not visibly contain a name placeholder
# in these two variants. Do not guess their provider variable contract.
FIELD_REVIEW = frozenset({"2regresa_299_n3", "7regresa_399_n2"})
MAPPING = {"1": "first_name"}
PURPOSE = "REACTIVATION"


def expected_names(branch: str) -> tuple[str, ...]:
    if branch not in COSTA:
        raise ValueError(f"Sucursal fuera del alcance Costa: {branch}")
    families = (*REGULAR_FAMILIES, LOMA_FAMILY if branch == "LOMA_BONITA" else OTHER_COAST_FAMILY)
    return tuple(f"{number}regresa_{family}" for family in families for number in range(1, 9))


@dataclass(frozen=True)
class LinkPlanRow:
    name: str
    status: str
    branches: tuple[str, ...]
    channels: tuple[str, ...]
    reasons: tuple[str, ...] = ()


def _active_bindings(bindings: list[dict]) -> dict[str, dict]:
    by_branch: dict[str, list[dict]] = defaultdict(list)
    for item in bindings:
        if item["sucursal_canon"] in COSTA and item["is_active"] and item["is_default"]:
            by_branch[item["sucursal_canon"]].append(item)
    if any(len(by_branch[branch]) != 1 for branch in COSTA):
        raise ValueError("Falta un canal activo y predeterminado único para cada sucursal Costa.")
    channels = [by_branch[branch][0]["provider_channel_id"] for branch in COSTA]
    if len(set(channels)) != len(channels):
        raise ValueError("Dos sucursales Costa tienen el mismo canal de iVentas.")
    return {branch: by_branch[branch][0] for branch in COSTA}


def build_plan(bindings: list[dict], inventories: dict[str, tuple], catalog: list[dict]) -> list[LinkPlanRow]:
    """Only existing, provider-approved exact pairs may be linked."""
    branches = _active_bindings(bindings)
    if set(inventories) != set(COSTA):
        raise ValueError("El inventario no cubre exactamente las siete sucursales Costa.")

    provider_status = {}
    for branch in COSTA:
        channel = branches[branch]["provider_channel_id"]
        for item in inventories[branch]:
            if item.channel_id != channel:
                continue
            key = (branch, item.template_name.casefold())
            prior = provider_status.get(key)
            if prior is not None and prior != item.status:
                raise ValueError("iVentas devolvió estados de aprobación contradictorios.")
            provider_status[key] = item.status

    current = {}
    for item in catalog:
        key = item["template_name"].casefold()
        if key in current:
            raise ValueError("Hay nombres duplicados de plantilla en el catálogo Suite.")
        current[key] = item

    names = sorted(set(name for branch in COSTA for name in expected_names(branch)))
    rows = []
    for name in names:
        scope = tuple(branch for branch in COSTA if name in expected_names(branch))
        channels = tuple(sorted(branches[branch]["provider_channel_id"] for branch in scope))
        missing = tuple(
            f"{branch}:{provider_status.get((branch, name), 'not_observed')}"
            for branch in scope if provider_status.get((branch, name)) != "accepted"
        )
        existing = current.get(name)
        if missing:
            status, reasons = "PENDING_APPROVAL", missing
        elif name in FIELD_REVIEW:
            status, reasons = "VERIFY_FIELDS", ("Campo personalizado no visible en el texto fuente.",)
        elif existing is None:
            status, reasons = "READY", ()
        elif (existing["provider"] == "IVENTAS"
              and existing["is_active"]
              and "REACTIVATION" in existing["purposes"]
              and existing["variables"] == MAPPING
              and set(existing["compatible_channel_ids"]) == set(channels)):
            status, reasons = "ALREADY_LINKED", ()
        else:
            status, reasons = "CONFLICT", ("La plantilla ya existe con otra configuración; no se sobrescribe.",)
        rows.append(LinkPlanRow(name, status, scope, channels, reasons))
    return rows


def _load_inventories(bindings: dict[str, dict]) -> dict[str, tuple]:
    credentials = load_iventas_template_credentials(session=db.session)
    missing = [branch for branch in COSTA if bindings[branch]["sucursal_id"] not in credentials]
    if missing:
        raise ValueError("Faltan accesos de iVentas para: " + ", ".join(missing))
    db.session.remove()
    results = {}
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        try:
            for branch in COSTA:
                branch_id = bindings[branch]["sucursal_id"]
                results[branch] = read_template_inventory(browser, credentials[branch_id])
                print(f"Inventario autenticado: {branch} ({len(results[branch])} registros).")
        finally:
            browser.close()
    return results


def _verify_actor(actor_id: int) -> None:
    user = db.session.get(UserORM, actor_id)
    if user is None:
        raise ValueError("El usuario autorizado no existe.")
    access = resolve_marketing_access(user)
    if not (access.is_global and access.can_manage_dispatch_config
            and access.can_manage_campaigns):
        raise ValueError("El usuario carece de permisos globales de configuración de campañas.")


def main() -> None:
    cli = argparse.ArgumentParser(description="Vincular 32 plantillas Costa aprobadas, sin envíos")
    cli.add_argument("--apply", action="store_true", help="Registrar únicamente filas READY en Suite")
    cli.add_argument("--actor-id", type=int, help="Usuario global responsable de la vinculación")
    cli.add_argument("--confirm", help="Frase obligatoria para escritura")
    args = cli.parse_args()
    if args.apply and (not args.actor_id or args.confirm != "VINCULAR_COSTA"):
        cli.error("--apply requiere --actor-id y --confirm VINCULAR_COSTA")

    with create_app().app_context():
        if args.apply:
            _verify_actor(args.actor_id)
        bindings = _active_bindings(list_channel_bindings(active_only=True, session=db.session))
        inventories = _load_inventories(bindings)
        catalog = list_templates(active_only=False, session=db.session)
        plan = build_plan(list(bindings.values()), inventories, catalog)
        created = 0
        for row in plan:
            reason = "; ".join(row.reasons)
            print(f"{row.name}: {row.status} | {len(row.branches)} canales" +
                  (f" | {reason}" if reason else ""))
            if args.apply and row.status == "READY":
                save_template(
                    provider="IVENTAS", template_name=row.name, label=row.name,
                    is_active=True, purposes=[PURPOSE], variables=MAPPING,
                    compatible_channel_ids=list(row.channels),
                    actor_user_id=args.actor_id,
                    metadata={"linked_from": "AUTHENTICATED_IVENTAS_APPROVAL",
                              "observed_at": datetime.now(timezone.utc).isoformat()},
                    require_explicit_channels=True, session=db.session,
                )
                created += 1
        tally = defaultdict(int)
        for row in plan:
            tally[row.status] += 1
        print(f"Resumen: {dict(sorted(tally.items()))}. Vinculadas en esta ejecución: {created}.")
        print("No se crearon plantillas en iVentas ni se enviaron WhatsApps.")


if __name__ == "__main__":
    main()
