"""Guarded Campaign V2 #15 suppression of phones actually submitted in #14.

Usage (after reviewed migration and deployment):
    python scripts/apply_winback_general_previous_submit_exclusions.py
    python scripts/apply_winback_general_previous_submit_exclusions.py --apply

Dry-run is read-only. Apply writes audited exclusions ONLY; no WhatsApp calls.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import create_app
from app.extensions import db
from app.models.marketing import (
    MarketingCampaignV2ORM,
    MarketingCampaignV2RecipientORM,
    MarketingCampaignV2ProviderCampaignORM,
)
from app.models.user_model import UserORM
from app.services.marketing_access import resolve_marketing_access
from app.services.marketing_campaign_v2_dispatch_exclusion_service import (
    add_campaign_v2_previous_campaign_contact_exclusions,
    find_previous_campaign_contact_ids,
    get_campaign_v2_excluded_recipient_ids,
)

SOURCE = 14
TARGET = 15
EXPECTED_MATCHES = 162
EXPECTED_SUBMITTED = 10671
EXPECTED_FROZEN = 74963


def run(*, apply: bool) -> None:
    app = create_app()
    with app.app_context():
        try:
            actor = UserORM.get_by_username("admicorp")
            if actor is None:
                raise RuntimeError("Actor ADMICORP no encontrado.")
            access = resolve_marketing_access(actor)
            if not access.is_global or not access.can_manage_dispatch_config:
                raise RuntimeError("Actor no autorizado para exclusiones globales.")

            source = db.session.get(MarketingCampaignV2ORM, SOURCE)
            target = db.session.get(MarketingCampaignV2ORM, TARGET)
            if (
                source is None or target is None
                or source.name != "WINBACK_BCN_OCTUBRE_2026"
                or target.name != "WINBACK_GENERAL_OCTUBRE_2026"
                or source.frozen_at is None or target.frozen_at is None
            ):
                raise RuntimeError("Identidad o estado congelado incorrecto.")
            if target.purpose != "REACTIVATION" or target.source != "EXPIRED_MEMBERS":
                raise RuntimeError("Clasificación de campaña destino incorrecta.")
            filters = (target.audience_definition_json or {}).get("filters") or {}
            if (
                str(filters.get("adeudo_min")) not in {"0", "0.0", "0.00"}
                or str(filters.get("adeudo_max")) not in {"0", "0.0", "0.00"}
                or filters.get("audience_families") != ["DOMICILIADO"]
                or filters.get("excluded_sucursal_keys") != ["SERRANIA"]
            ):
                raise RuntimeError("Los filtros congelados cambiaron.")

            frozen = db.session.query(MarketingCampaignV2RecipientORM).filter_by(
                campaign_id=TARGET
            ).count()
            if frozen != EXPECTED_FROZEN:
                raise RuntimeError("La cohorte congelada cambió.")
            if db.session.query(MarketingCampaignV2ProviderCampaignORM.id).filter_by(
                campaign_v2_id=TARGET
            ).first():
                raise RuntimeError("El destino ya tiene provider children.")

            proof = find_previous_campaign_contact_ids(
                campaign_id=TARGET, source_campaign_id=SOURCE,
                allowed_sucursal_keys=None, session=db.session,
            )
            if (
                proof["source_submitted_phones_count"] != EXPECTED_SUBMITTED
                or proof["matched"] != EXPECTED_MATCHES
            ):
                raise RuntimeError("La evidencia de contactos previos cambió.")

            existing = get_campaign_v2_excluded_recipient_ids(
                campaign_id=TARGET, session=db.session,
            )
            if existing - set(proof["matched_recipient_ids"]):
                raise RuntimeError("Existen exclusiones no revisadas para #15.")

            print("TARGET_CAMPAIGN_ID =", TARGET)
            print("SOURCE_SUBMITTED_CAMPAIGN_ID =", SOURCE)
            print("FROZEN =", frozen)
            print("SOURCE_SUBMITTED_PHONES =", proof["source_submitted_phones_count"])
            print("MATCHED_PREVIOUS_CONTACTS =", proof["matched"])
            print("ALREADY_EXCLUDED =", len(existing))
            print("PROJECTED_SENDABLE_BEFORE_OTHER_SUPPRESSIONS =", frozen - EXPECTED_MATCHES)
            print("ACTION =", "APPLY" if apply else "DRY_RUN")

            if apply:
                result = add_campaign_v2_previous_campaign_contact_exclusions(
                    campaign_id=TARGET, source_campaign_id=SOURCE,
                    actor_user_id=int(actor.id), expected_count=EXPECTED_MATCHES,
                    allowed_sucursal_keys=None, session=db.session,
                )
                db.session.commit()
                after = get_campaign_v2_excluded_recipient_ids(
                    campaign_id=TARGET, session=db.session,
                )
                if after != set(proof["matched_recipient_ids"]):
                    raise RuntimeError("Verificar exclusiones posteriores a commit.")
                print("ADDED =", result["added"])
                print("ALREADY_PRESENT =", result["already_present"])
                print("EXCLUSIONS_AFTER =", len(after))
                print("EXCLUSIONES_GENERAL_OK")
            else:
                db.session.rollback()
                print("DRY_RUN_OK")
        except Exception:
            db.session.rollback()
            raise
        finally:
            db.session.remove()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Winback #15: prior submitted contacts only")
    parser.add_argument("--apply", action="store_true")
    run(apply=parser.parse_args().apply)
