from __future__ import annotations

import json
import sys

from app.wsgi import app
from app.services.marketing_campaign_v2_qa_manual_service import (
    build_campaign_v2_qa_manual_preview,
    freeze_campaign_v2_qa_manual,
)


def _read_payload() -> dict:
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"JSON inválido: {exc}") from exc
    if not isinstance(payload, dict):
        raise SystemExit("El payload debe ser un objeto JSON.")
    return payload


def main() -> int:
    if len(sys.argv) != 2 or sys.argv[1] not in {"preview", "freeze"}:
        raise SystemExit(
            "Uso: python scripts/marketing/campaign_v2_qa_smoke.py [preview|freeze]"
        )

    mode = sys.argv[1]
    payload = _read_payload()

    with app.app_context():
        common = {
            "name": payload.get("name"),
            "purpose": payload.get("purpose"),
            "sucursal_id": payload.get("sucursal_id"),
            "recipients": payload.get("recipients"),
        }
        if mode == "preview":
            result = build_campaign_v2_qa_manual_preview(**common)
        else:
            result = freeze_campaign_v2_qa_manual(
                **common,
                expected_preview_fingerprint=payload.get(
                    "expected_preview_fingerprint"
                ),
                created_by_user_id=payload.get("created_by_user_id"),
            )

    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
