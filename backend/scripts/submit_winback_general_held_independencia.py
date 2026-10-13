"""One-off #15: persist INDEPENDENCIA and INSURGENTES HELD; submit other 23.

Dry-run by default (strictly read-only). --apply sends REAL iVentas broadcasts.
NEVER re-run --apply after an attempt. Reconcile persisted children instead.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import create_app
from app.extensions import db
from app.integrations.iventas.broadcast_provider import IVentasBroadcastProvider
from app.models.marketing import (
    MarketingCampaignV2ORM,
    MarketingCampaignV2RecipientDispatchExclusionORM,
)
from app.models.user_model import UserORM
from app.services.marketing_access import resolve_marketing_access
from app.services.marketing_campaign_v2_partial_resume_service import (
    continue_ready_children,
    review_partial_resume,
)
from app.services.marketing_campaign_v2_preflight_service import (
    build_campaign_v2_preflight,
)
from app.services.marketing_campaign_v2_submit_service import (
    _prepare_provider_campaign_rows,
    get_campaign_v2_submit_state,
)

CAMPAIGN_ID = 15
TEMPLATE_ID = 3
FINGERPRINT = "fa57395ae86547ac73672e762bc0fd832c3486028514eda8544c0c3d6c59faca"
HELD_BRANCHES = {"INDEPENDENCIA": 3612, "INSURGENTES": 68}
HELD_CAP = 250
TOTAL_COUNT = 74175
SEND_COUNT = TOTAL_COUNT - sum(HELD_BRANCHES.values())  # 70,495
BATCH_COUNT = 25
HELD_REASON = "CHANNEL_DAILY_QUOTA"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError("ENVIO_BLOQUEADO: " + message)


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true",
                        help="Envío REAL: 25 children, 2 HELD y 23 envíos")
    parser.add_argument("--acknowledge-quota-uncertainty", action="store_true",
                        help="Reconoce que no hay capacidad restante Meta verificada para los otros 23 canales")
    parser.add_argument("--approved-contact-count", type=int, default=None,
                        help="Confirmar exactamente 70495 envíos")
    return parser.parse_args()


def main() -> int:
    args = _arguments()
    app = create_app()
    with app.app_context():
        try:
            actor = UserORM.get_by_username("admicorp")
            require(actor is not None, "Actor ADMICORP no encontrado")
            access = resolve_marketing_access(actor)
            require(
                access.is_global and access.can_send_campaigns
                and access.can_manage_dispatch_config,
                "Actor no autorizado para retención y envío",
            )

            # The web process remains OFF. Only --apply, in its own isolated
            # docker exec process, is allowed to request process-local ON.
            require(
                bool(app.config.get("CAMPAIGN_V2_PROVIDER_SEND_ENABLED")) is args.apply,
                "Kill switch del proceso incorrecto: dry-run=OFF, apply=ON",
            )

            campaign = db.session.get(MarketingCampaignV2ORM, CAMPAIGN_ID)
            require(
                campaign is not None
                and campaign.name == "WINBACK_GENERAL_OCTUBRE_2026"
                and campaign.purpose == "REACTIVATION"
                and campaign.source == "EXPIRED_MEMBERS"
                and campaign.frozen_at is not None,
                "Campaña congelada incorrecta",
            )

            state = get_campaign_v2_submit_state(
                campaign_id=CAMPAIGN_ID, session=db.session,
            )
            require(
                state["status"] == "NOT_STARTED"
                and not state["has_provider_campaigns"],
                "Ya existe un intento; no reintentar ni reemplazar children",
            )

            plan = build_campaign_v2_preflight(
                campaign_id=CAMPAIGN_ID,
                template_id=TEMPLATE_ID,
                allowed_sucursal_keys=None,
                session=db.session,
            )
            require(plan.ready and plan.mode == "IMMEDIATE", "Preflight bloqueado")
            require(plan.dispatch_fingerprint == FINGERPRINT, "Fingerprint cambió")
            require(plan.campaign_name == campaign.name, "Nombre de campaña cambió")
            require(plan.provider == "IVENTAS", "Proveedor incorrecto")
            require(plan.frozen_count == 74963, "Cohorte congelada cambió")
            require(len(plan.campaign_excluded_recipient_ids) == 788, "Exclusiones cambiaron")
            require(len(plan.sendable_phones) == TOTAL_COUNT, "Enviables cambiaron")
            require(not plan.blacklisted_phones, "Blacklist cambió")
            require(len(plan.batches) == BATCH_COUNT, "Cantidad de lotes cambió")
            require(
                len(set(plan.sendable_phones)) == TOTAL_COUNT,
                "Teléfonos enviables duplicados",
            )
            require(
                sum(len(batch.recipients) for batch in plan.batches) == TOTAL_COUNT,
                "Suma de lotes incorrecta",
            )
            require(
                all(
                    batch.ready
                    and batch.template_id == TEMPLATE_ID
                    and batch.template_name == "winback_general_octubre"
                    and bool(batch.provider_channel_id)
                    and batch.sucursal_canon != "SERRANIA"
                    for batch in plan.batches
                ),
                "Lote/plantilla/canal no autorizado",
            )
            require(
                len({batch.provider_channel_id for batch in plan.batches}) == BATCH_COUNT,
                "Canales repetidos",
            )
            by_branch = {batch.sucursal_canon: batch for batch in plan.batches}
            require(len(by_branch) == BATCH_COUNT, "Sucursal repetida")
            require(
                all(
                    name in by_branch
                    and len(by_branch[name].recipients) == count
                    for name, count in HELD_BRANCHES.items()
                ) and HELD_BRANCHES["INDEPENDENCIA"] > HELD_CAP,
                "Sucursales retenidas cambiaron",
            )
            expected_ready = {
                name: len(batch.recipients)
                for name, batch in by_branch.items()
                if name not in HELD_BRANCHES
            }
            require(
                len(expected_ready) == 23
                and sum(expected_ready.values()) == SEND_COUNT,
                "Manifest de 23 lotes cambió",
            )
            require(
                all(0 < count <= 100000 for count in expected_ready.values()),
                "Lote supera límites diarios reportados",
            )

            exclusions = (
                db.session.query(MarketingCampaignV2RecipientDispatchExclusionORM)
                .filter_by(campaign_id=CAMPAIGN_ID)
                .all()
            )
            counts = Counter(row.reason for row in exclusions)
            require(
                len(exclusions) == 788
                and counts == {
                    "PREVIOUS_CAMPAIGN_CONTACT": 162,
                    "AMBIGUOUS_BRANCH_EVIDENCE": 626,
                }
                and all(
                    row.related_campaign_id == 14
                    for row in exclusions
                    if row.reason == "PREVIOUS_CAMPAIGN_CONTACT"
                ),
                "Auditoría de exclusiones cambió",
            )

            print("=== MANIFEST WINBACK GENERAL #15 ===", flush=True)
            print("FINGERPRINT =", plan.dispatch_fingerprint)
            print("CONGELADOS =", plan.frozen_count)
            print("ENVIABLES =", len(plan.sendable_phones))
            for branch, count in HELD_BRANCHES.items():
                print("HELD =", branch, count, "cap_reportado =", HELD_CAP)
            print("READY_BATCHES =", len(expected_ready))
            print("READY_RECIPIENTS =", sum(expected_ready.values()))
            print("INSURGENTES_RETENIDA = TRUE")
            print("CUPO_RESTANTE_OTROS_23_NO_VERIFICADO_POR_META = True")
            print("OPERACION =", "APPLY_REAL_SEND" if args.apply else "READ_ONLY")
            print("PROVIDER_CALLS_PREPARATION = 0", flush=True)

            if not args.apply:
                print("DRY_RUN_OK = TRUE")
                return 0

            # Only reported nominal limits exist; do not claim live quota was checked.
            require(
                args.acknowledge_quota_uncertainty is True,
                "Debes reconocer que no se pudo verificar cupo restante Meta",
            )
            require(
                args.approved_contact_count == SEND_COUNT,
                "Total exacto de contactos no autorizado",
            )

            key = str(app.config.get("IVENTAS_CAMPAIGN_SEND_API_KEY") or "")
            base_url = str(app.config.get("IVENTAS_CAMPAIGN_SEND_API_BASE_URL") or "").rstrip("/")
            require(
                key.startswith("ivk_live_")
                and base_url == "https://rest.iventas.mx",
                "Configuración iVentas producción incorrecta",
            )
            provider = IVentasBroadcastProvider(api_key=key, base_url=base_url)
            attested_at = datetime.now(timezone.utc)
            hold_manifest = {
                branch: {
                    "reason": HELD_REASON,
                    "evidence": {
                        "kind": "CHANNEL_DAILY_QUOTA",
                        "reported_daily_cap": HELD_CAP,
                        "held_recipient_count": count,
                        "reason": "OPERATOR_HELD_LIMITED_PORTFOLIO",
                        "remaining_capacity_unverified": True,
                        "approved_ready_recipient_count": SEND_COUNT,
                        "attested_at_utc": attested_at.isoformat(),
                        "operator_user_id": int(actor.id),
                    },
                }
                for branch, count in HELD_BRANCHES.items()
            }

            # ONE DB commit of all children: 23 READY + two HELD.
            # No provider call can happen before durable hold state.
            _prepare_provider_campaign_rows(
                plan=plan,
                actor_user_id=int(actor.id),
                session=db.session,
                now=attested_at,
                held_batches=hold_manifest,
            )

            review = review_partial_resume(
                campaign_id=CAMPAIGN_ID,
                template_id=TEMPLATE_ID,
                expected_fingerprint=FINGERPRINT,
                expected_submitted={},
                expected_failed={},
                expected_ready=expected_ready,
                expected_held={
                    branch: (count, HELD_REASON)
                    for branch, count in HELD_BRANCHES.items()
                },
                session=db.session,
            )
            require(
                len(review.ready_children) == 23
                and sum(len(c.batch.recipients) for c in review.ready_children)
                == SEND_COUNT,
                "Revisión post-persistencia no coincide; NO enviar",
            )

            print("HELD_PERSISTED = TRUE", flush=True)
            print("INICIANDO_ENVIO_REAL_23_LOTES = TRUE", flush=True)
            results = continue_ready_children(
                review=review,
                actor_user_id=int(actor.id),
                provider=provider,
                send_enabled=True,
                session=db.session,
            )
            print("=== RESULTADO ENVIO PARCIAL ===", flush=True)
            for branch, status, provider_id_or_error in results:
                print(
                    branch, "|", status, "|",
                    provider_id_or_error or "-", flush=True,
                )
            accepted = sum(1 for _, status, _ in results if status == "SUBMITTED")
            print("NEW_SUBMITTED_BATCHES =", accepted)
            print("UNATTEMPTED_READY =", 23 - len(results))
            for branch, count in HELD_BRANCHES.items():
                print(branch + "_HELD =", count)
            if len(results) != 23 or accepted != 23:
                print("PARTIAL_FAILURE = TRUE; DO_NOT_RERUN_APPLY", flush=True)
                return 2
            print("PARTIAL_SUBMIT_ACCEPTED = TRUE")
            print("NOTE = Accepted by iVentas, not delivered by Meta")
            return 0

        except Exception as exc:
            db.session.rollback()
            print("OPERACION_DETENIDA =", str(exc), flush=True)
            raise
        finally:
            db.session.remove()


if __name__ == "__main__":
    raise SystemExit(main())
