"""Campaign #8 partial continuation. DRY RUN by default; --apply sends REAL broadcasts.

This is an intentionally campaign-specific, single-use production tool.
Do not reset existing children, regenerate the cohort, or retry on failure.
"""
from __future__ import annotations

import argparse
from collections import Counter

from app import create_app
from app.extensions import db
from app.models.user_model import UserORM
from app.services.marketing_access import resolve_marketing_access
from app.services.marketing_campaign_v2_partial_resume_service import (
    continue_ready_children,
    review_partial_resume,
)
from app.integrations.iventas.broadcast_provider import IVentasBroadcastProvider

CAMPAIGN_ID = 8
TEMPLATE_ID = 1
FINGERPRINT = "30881c47615db3b227eeea9a5d10ee079b798914657a95e744c6b852b1d1c25d"

# Original provider IDs are part of the guard: NEVER submit an accepted branch.
SUBMITTED = {
    "AZAHARES_CUL": (573, "6ac83b0ba95d0f0008bd0926"),
    "CARROUSEL_TJ": (702, "6ac83b0ca95d0f0008bd0927"),
    "INDEPENDENCIA": (581, "6ac83b0c180ec400090d5c42"),
    "INSURGENTES": (350, "6ac83b0df5c20300091bd05a"),
    "IXTAPALUCA": (384, "6ac83b0df5c20300091bd05b"),
    "LOMA_BONITA": (217, "6ac83b0ef5c20300091bd066"),
    "METEPEC": (647, "6ac83b0ff5c20300091bd067"),
    "MISION_ENS": (807, "6ac83b0fa95d0f0008bd0952"),
    "PABELLON_RTO": (358, "6ac83b12a95d0f0008bd095f"),
    "PAPALOTE_TJ": (276, "6ac83b14f5c20300091bd09b"),
    "PASEO_2000": (955, "6ac83b15f5c20300091bd09c"),
}
# The failed row is kept as PROVIDER_ERROR with its ORIGINAL evidence.
# This is an authorized omission from this continuation, not a retry.
FAILED_SKIPPED = {
    "PASEO_LA_PAZ": (170, "TEMPLATE_NOT_FOUND", "bc-mv09582n-ly0gq0"),
}
READY = {
    "SALTILLO_VILLALTA": 211,
    "SAN_ISIDRO_CUL": 605,
    "SAN_LUIS": 487,
    "SANTA_FE": 701,
    "SEND_CHIH": 79,
    "SEND_CUL": 791,
    "SEND_MXL": 914,
    "SEND_SALTILLO": 1089,
    "SERRANIA": 382,
    "STA_CATARINA": 128,
    "TEC_MXL": 793,
    "TLALNEPANTLA": 789,
    "VILLAS_DEL_REY": 437,
    "VILLA_VERDE": 573,
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="REAL SEND: submit only 14 READY children")
    args = parser.parse_args()

    app = create_app()
    with app.app_context():
        try:
            actor = UserORM.get_by_username("admicorp")
            if actor is None:
                raise RuntimeError("Operator admicorp not found.")
            access = resolve_marketing_access(actor)
            if not (access.is_global and access.can_send_campaigns):
                raise RuntimeError("Operator has no global Campaign V2 send permission.")

            send_enabled = app.config["CAMPAIGN_V2_PROVIDER_SEND_ENABLED"]
            if bool(send_enabled) != bool(args.apply):
                raise RuntimeError(
                    "Process-local kill switch mismatch: dry-run requires OFF; "
                    "--apply requires process-local ON."
                )
            if sum(count for count, _ in SUBMITTED.values()) != 5850:
                raise RuntimeError("Accepted manifest corrupt.")
            if sum(READY.values()) != 7979:
                raise RuntimeError("Pending manifest corrupt.")

            plan_review = review_partial_resume(
                campaign_id=CAMPAIGN_ID,
                template_id=TEMPLATE_ID,
                expected_fingerprint=FINGERPRINT,
                expected_submitted=SUBMITTED,
                expected_failed=FAILED_SKIPPED,
                expected_ready=READY,
                session=db.session,
            )
            plan = plan_review.plan
            if (
                plan.campaign_name != "Socios activos/venta nueva invita y gana"
                or plan.campaign_purpose != "NEW_SALE"
                or plan.provider != "IVENTAS"
                or plan.frozen_count != 14002
                or len(plan.sendable_phones) != 13999
                or len(set(plan.sendable_phones)) != 13999
                or len(plan.blacklisted_phones) != 0
                or set(plan.campaign_excluded_recipient_ids) != {59510, 59859, 60120}
                or len(plan.batches) != 26
                or len(plan_review.ready_children) != 14
                or sum(len(b.recipients) for b in plan.batches) != 13999
                or any(b.template_name != "invita_y_gana_4800" for b in plan.batches)
            ):
                raise RuntimeError("Campaign #8 authorized dispatch invariants changed.")

            print("VALIDACION_REANUDACION = OK", flush=True)
            print("CAMPAIGN_ID = 8", flush=True)
            print("FINGERPRINT =", plan.dispatch_fingerprint, flush=True)
            print("YA_ACEPTADOS = 11 / 5850", flush=True)
            print("PASEO_LA_PAZ_OMITIDO = 1 / 170", flush=True)
            print("PENDIENTES_A_ENVIAR = 14 / 7979", flush=True)
            print("OPERACION =", "APPLY_REAL_SEND" if args.apply else "DRY_RUN", flush=True)

            if not args.apply:
                for child in plan_review.ready_children:
                    print("READY =", child.batch.sucursal_canon, len(child.batch.recipients))
                print("ENVIO_REAL = NO EJECUTADO", flush=True)
                return 0

            key = app.config.get("IVENTAS_CAMPAIGN_SEND_API_KEY", "")
            base_url = str(app.config.get("IVENTAS_CAMPAIGN_SEND_API_BASE_URL", "")).rstrip("/")
            if not key.startswith("ivk_live_") or base_url != "https://rest.iventas.mx":
                raise RuntimeError("Live iVentas provider config unexpected; no send.")
            provider = IVentasBroadcastProvider(api_key=key, base_url=base_url)
            print("INICIANDO_CONTINUACION_REAL = TRUE", flush=True)
            outcomes = continue_ready_children(
                review=plan_review,
                actor_user_id=int(actor.id),
                provider=provider,
                send_enabled=True,
                session=db.session,
            )
            print("=== RESULTADO_REANUDACION ===", flush=True)
            for branch, status, provider_id_or_error in outcomes:
                print(branch, "|", status, "|", provider_id_or_error or "-", flush=True)
            status_counts = Counter(status for _, status, _ in outcomes)
            print("NUEVOS_ACEPTADOS =", status_counts.get("SUBMITTED", 0), flush=True)
            print("NO_INTENTADOS =", 14 - len(outcomes), flush=True)
            print("PASEO_LA_PAZ_CONSERVA_PROVIDER_ERROR = True", flush=True)
            if len(outcomes) != 14 or status_counts.get("SUBMITTED", 0) != 14:
                print("REANUDACION_INCOMPLETA = TRUE; NO REINTENTAR", flush=True)
                return 2
            print("REANUDACION_COMPLETA = TRUE", flush=True)
            return 0
        finally:
            db.session.remove()


if __name__ == "__main__":
    raise SystemExit(main())
