from __future__ import annotations

from datetime import date

from app import db
from app.models.rpa import GascaSmsRequestORM, GascaSmsRequestStatus
from app.rpa.services.gasca_sms_code_lookup_service import (
    GascaSmsCodeLookupError,
    lookup_gasca_sms_code,
    mask_code,
    mask_phone,
    normalize_pin,
    phone_digits,
)
from app.rpa.services.google_messages_sms_sender_service import (
    GoogleMessagesSmsSenderError,
    send_sms_via_google_messages,
)


class GascaSmsRequestServiceError(RuntimeError):
    pass


class GascaSmsRequestMotivo:
    HUELLA_NO_LEIDA = "HUELLA_NO_LEIDA"
    VISITA_PROSPECTO = "VISITA_PROSPECTO"
    SMS_NO_LLEGA = "SMS_NO_LLEGA"
    OTRO = "OTRO"

    ALL = (
        HUELLA_NO_LEIDA,
        VISITA_PROSPECTO,
        SMS_NO_LLEGA,
        OTRO,
    )


def validate_motivo(motivo: str) -> str:
    normalized = (motivo or "").strip().upper()
    if normalized not in GascaSmsRequestMotivo.ALL:
        raise ValueError(
            "Motivo inválido. Permitidos: "
            + ", ".join(GascaSmsRequestMotivo.ALL)
        )
    return normalized


def validate_phone_digits(phone_raw: str) -> str:
    digits = phone_digits(phone_raw)
    if not digits:
        raise ValueError("Teléfono vacío o inválido.")

    if len(digits) < 8:
        raise ValueError("Teléfono inválido: se esperaban al menos 8 dígitos.")

    if len(digits) > 15:
        raise ValueError("Teléfono inválido: se esperaban máximo 15 dígitos.")

    return digits


def build_gasca_sms_message(code: str) -> str:
    clean_code = (code or "").strip()

    if not clean_code:
        raise GascaSmsRequestServiceError(
            "No se puede enviar SMS porque Gasca no devolvió código."
        )

    return f"Ultra Gym: tu código de acceso es {clean_code}. No compartas este código."


def sanitize_lookup_result_for_storage(result: dict) -> dict:
    sanitized = dict(result or {})
    selected = dict(sanitized.get("selected") or {})

    if selected:
        selected["telefono"] = mask_phone(selected.get("telefono") or "")
        selected["codigo"] = mask_code(selected.get("codigo") or "")

    sanitized["selected"] = selected
    return sanitized


def mask_sms_message_for_storage(message: str, code: str) -> str:
    masked_code = mask_code(code)
    return (message or "").replace(code, masked_code)



def _apply_lookup_result_to_request(
    request: GascaSmsRequestORM,
    result: dict,
) -> None:
    request.status = result.get("status") or GascaSmsRequestStatus.FAILED
    request.user_message = result.get("user_message")

    selected = result.get("selected") or {}
    if selected:
        request.gasca_nombre_masked = selected.get("nombre")
        request.gasca_phone_masked = selected.get("telefono")
        request.gasca_code_masked = selected.get("codigo")
        request.gasca_generated_raw = selected.get("generado")
        request.gasca_used_raw = selected.get("utilizado")
        request.gasca_sucursal = selected.get("sucursal")

    if request.status in {
        GascaSmsRequestStatus.READY_TO_SEND,
        GascaSmsRequestStatus.MULTIPLE_CANDIDATES_SELECTED_LATEST,
    }:
        request.status = GascaSmsRequestStatus.READY_TO_SEND


def create_gasca_sms_request(
    *,
    pin_raw: str,
    phone_raw: str,
    motivo: str,
    motivo_detalle: str | None = None,
    requested_by_user_id: int | None = None,
    sucursal_id: int | None = None,
) -> GascaSmsRequestORM:
    pin_normalized = normalize_pin(pin_raw)
    requested_phone_digits = validate_phone_digits(phone_raw)
    motivo_normalized = validate_motivo(motivo)

    request = GascaSmsRequestORM(
        pin_raw=(pin_raw or "").strip(),
        pin_normalized=pin_normalized,
        requested_phone_raw=(phone_raw or "").strip(),
        requested_phone_digits=requested_phone_digits,
        requested_phone_masked=mask_phone(phone_raw),
        motivo=motivo_normalized,
        motivo_detalle=(motivo_detalle or "").strip() or None,
        status=GascaSmsRequestStatus.PENDING,
        requested_by_user_id=requested_by_user_id,
        sucursal_id=sucursal_id,
        attempt_count=0,
    )

    db.session.add(request)
    db.session.flush()

    return request


def process_gasca_sms_request(
    request: GascaSmsRequestORM,
    *,
    today: date | None = None,
    headless: bool = True,
) -> GascaSmsRequestORM:
    request.status = GascaSmsRequestStatus.GASCA_SEARCHING
    request.attempt_count = (request.attempt_count or 0) + 1
    request.last_attempt_at = db.func.now()
    db.session.flush()

    try:
        from app.rpa.services.gasca_sms_code_lookup_service import resolve_config_from_env

        result = lookup_gasca_sms_code(
            pin_raw=request.pin_normalized,
            phone_raw=request.requested_phone_raw,
            config=resolve_config_from_env(headless=headless),
            today=today,
            show_sensitive=True,
        )

        selected = result.get("selected") or {}
        gasca_code_real = (selected.get("codigo") or "").strip()

        _apply_lookup_result_to_request(
            request,
            sanitize_lookup_result_for_storage(result),
        )
        request.processed_at = db.func.now()

        if request.status == GascaSmsRequestStatus.READY_TO_SEND:
            sms_message = build_gasca_sms_message(gasca_code_real)

            request.status = GascaSmsRequestStatus.SMS_SENDING
            request.sms_provider = "google_messages_web"
            request.sms_message_masked = mask_sms_message_for_storage(
                sms_message,
                gasca_code_real,
            )
            db.session.flush()

            sms_result = send_sms_via_google_messages(
                phone=request.requested_phone_raw,
                message=sms_message,
            )

            if not sms_result.get("ok"):
                raise GoogleMessagesSmsSenderError(
                    f"Google Messages no confirmó envío: {sms_result}"
                )

            request.status = GascaSmsRequestStatus.SENT
            request.user_message = "SMS enviado correctamente por Google Messages."
            request.sent_at = db.func.now()
            request.processed_at = db.func.now()

    except (GascaSmsCodeLookupError, ValueError) as exc:
        request.status = GascaSmsRequestStatus.FAILED
        request.user_message = (
            "No se pudo procesar la solicitud. No fue posible consultar Gasca en este momento."
        )
        request.internal_error = str(exc)
        request.processed_at = db.func.now()

    except GoogleMessagesSmsSenderError as exc:
        request.status = GascaSmsRequestStatus.FAILED
        request.user_message = (
            "El código fue validado en Gasca, pero no se pudo enviar el SMS por Google Messages."
        )
        request.internal_error = str(exc)
        request.processed_at = db.func.now()

    except Exception as exc:
        request.status = GascaSmsRequestStatus.FAILED
        request.user_message = (
            "No se pudo procesar la solicitud. Ocurrió un error inesperado al consultar Gasca."
        )
        request.internal_error = repr(exc)
        request.processed_at = db.func.now()

    return request


def create_and_process_gasca_sms_request(
    *,
    pin_raw: str,
    phone_raw: str,
    motivo: str,
    motivo_detalle: str | None = None,
    requested_by_user_id: int | None = None,
    sucursal_id: int | None = None,
    today: date | None = None,
) -> GascaSmsRequestORM:
    request = create_gasca_sms_request(
        pin_raw=pin_raw,
        phone_raw=phone_raw,
        motivo=motivo,
        motivo_detalle=motivo_detalle,
        requested_by_user_id=requested_by_user_id,
        sucursal_id=sucursal_id,
    )

    process_gasca_sms_request(
        request,
        today=today,
    )

    db.session.commit()
    return request
