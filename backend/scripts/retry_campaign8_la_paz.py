"""Campaign #8 / Paseo La Paz controlled retry. DRY RUN unless --apply.

Run ONLY after the 14 READY children have been individually accepted.
Never repeat --apply after any attempt: inspect stored child/audit first.
"""
from __future__ import annotations

import argparse

from app import create_app
from app.extensions import db
from app.models.user_model import UserORM
from app.services.marketing_access import resolve_marketing_access
from app.integrations.iventas.broadcast_provider import IVentasBroadcastProvider
from app.services.marketing_campaign_v2_deterministic_rejection_retry import (
    review_campaign8_la_paz_retry,
    send_campaign8_la_paz_once,
)
from scripts.resume_campaign8_pending import SUBMITTED, READY, FINGERPRINT


ACCEPTED_COUNTS = {
    **{name: count for name, (count, _) in SUBMITTED.items()},
    **READY,
}
ORIGINAL_PROVIDER_IDS = {
    name: provider_id
    for name, (_, provider_id) in SUBMITTED.items()
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="REAL SEND of 170 recipients in Paseo La Paz")
    args = parser.parse_args()

    app = create_app()
    with app.app_context():
        try:
            actor = UserORM.get_by_username("admicorp")
            if actor is None:
                raise RuntimeError("Operator admicorp not found.")
            access = resolve_marketing_access(actor)
            if not (access.is_global and access.can_send_campaigns):
                raise RuntimeError("Operator not authorized for global Campaign V2 send.")
            if bool(app.config["CAMPAIGN_V2_PROVIDER_SEND_ENABLED"]) != bool(args.apply):
                raise RuntimeError("Process-local kill switch mismatch.")

            review = review_campaign8_la_paz_retry(
                fingerprint=FINGERPRINT,
                accepted_counts=ACCEPTED_COUNTS,
                original_provider_ids=ORIGINAL_PROVIDER_IDS,
                session=db.session,
            )
            print("VALIDACION_LA_PAZ = OK", flush=True)
            print("CAMPAIGN_ID = 8", flush=True)
            print("FINGERPRINT =", FINGERPRINT, flush=True)
            print("OTRAS_SUCURSALES_ACEPTADAS = 25 / 13829", flush=True)
            print("LA_PAZ = PROVIDER_ERROR / TEMPLATE_NOT_FOUND / 170", flush=True)
            print("OPERACION =", "APPLY_REAL_SEND" if args.apply else "DRY_RUN", flush=True)

            if not args.apply:
                print("ENVIO_REAL = NO EJECUTADO", flush=True)
                return 0

            key = app.config.get("IVENTAS_CAMPAIGN_SEND_API_KEY", "")
            base_url = str(app.config.get("IVENTAS_CAMPAIGN_SEND_API_BASE_URL", "")).rstrip("/")
            if not key.startswith("ivk_live_") or base_url != "https://rest.iventas.mx":
                raise RuntimeError("Invalid live iVentas integration configuration.")
            provider = IVentasBroadcastProvider(api_key=key, base_url=base_url)
            print("INICIANDO_ENVIO_REAL_LA_PAZ = TRUE", flush=True)
            status, reference = send_campaign8_la_paz_once(
                review=review,
                actor_user_id=int(actor.id),
                provider=provider,
                send_enabled=True,
                session=db.session,
            )
            print("RESULTADO_LA_PAZ =", status, flush=True)
            print("PROVIDER_ID_OR_ERROR =", reference or "-", flush=True)
            if status != "SUBMITTED":
                print("NO REINTENTAR: conciliar contra iVentas primero", flush=True)
                return 2
            print("ENVIOS_TOTALES_ACEPTADOS = 26 / 13999", flush=True)
            return 0
        finally:
            db.session.remove()


if __name__ == "__main__":
    raise SystemExit(main())
