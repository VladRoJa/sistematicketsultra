
from __future__ import annotations

import logging
import os
import signal
import time
from datetime import datetime, timedelta, timezone

from app import create_app, db
from app.models.rpa import GascaSmsRequestORM, GascaSmsRequestStatus
from app.rpa.services.gasca_sms_request_service import process_gasca_sms_request
from app.rpa.services.google_messages_sms_sender_service import (
    GoogleMessagesSmsSenderError,
    GoogleMessagesSmsSenderSession,
)


LOGGER = logging.getLogger("gasca_sms_worker")

POLL_INTERVAL_SECONDS = float(os.getenv("GASCA_SMS_WORKER_POLL_SECONDS", "2"))
IDLE_TIMEOUT_SECONDS = float(os.getenv("GASCA_SMS_WORKER_IDLE_TIMEOUT_SECONDS", "300"))
BATCH_SLEEP_SECONDS = float(os.getenv("GASCA_SMS_WORKER_BATCH_SLEEP_SECONDS", "0.5"))

_shutdown_requested = False


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _install_signal_handlers() -> None:
    def _handle_shutdown(signum, frame):
        global _shutdown_requested
        LOGGER.info("Señal recibida para detener worker Gasca SMS: %s", signum)
        _shutdown_requested = True

    signal.signal(signal.SIGTERM, _handle_shutdown)
    signal.signal(signal.SIGINT, _handle_shutdown)


def _claim_next_pending_request() -> GascaSmsRequestORM | None:
    request = (
        GascaSmsRequestORM.query
        .filter(GascaSmsRequestORM.status == GascaSmsRequestStatus.PENDING)
        .order_by(GascaSmsRequestORM.created_at.asc(), GascaSmsRequestORM.id.asc())
        .with_for_update(skip_locked=True)
        .first()
    )

    if request is None:
        db.session.rollback()
        return None

    request.status = GascaSmsRequestStatus.GASCA_SEARCHING
    request.user_message = "Solicitud tomada por el procesador SMS."
    request.last_attempt_at = db.func.now()
    db.session.flush()

    return request


def _has_pending_requests() -> bool:
    try:
        exists = (
            db.session.query(GascaSmsRequestORM.id)
            .filter(GascaSmsRequestORM.status == GascaSmsRequestStatus.PENDING)
            .limit(1)
            .first()
        )
        db.session.rollback()
        return exists is not None
    except Exception:
        db.session.rollback()
        raise


def _close_sender_session(sender_session: GoogleMessagesSmsSenderSession | None) -> None:
    if sender_session is None:
        return

    try:
        LOGGER.info("Cerrando sesión Google Messages por inactividad.")
        sender_session.close()
    except Exception:
        LOGGER.exception("Error cerrando sesión Google Messages.")
    finally:
        db.session.remove()


def run_worker_loop() -> None:
    global _shutdown_requested

    logging.basicConfig(
        level=os.getenv("GASCA_SMS_WORKER_LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )

    LOGGER.info(
        "Iniciando worker Gasca SMS. poll=%ss idle_timeout=%ss",
        POLL_INTERVAL_SECONDS,
        IDLE_TIMEOUT_SECONDS,
    )

    _install_signal_handlers()

    app = create_app()

    sender_session: GoogleMessagesSmsSenderSession | None = None
    last_activity_at: datetime | None = None

    with app.app_context():
        try:
            while not _shutdown_requested:
                request = None

                try:
                    request = _claim_next_pending_request()

                    if request is None:
                        if sender_session is not None and last_activity_at is not None:
                            idle_for = (_utc_now() - last_activity_at).total_seconds()

                            if idle_for >= IDLE_TIMEOUT_SECONDS:
                                # Grace check: antes de cerrar Chrome, revisa otra vez la cola.
                                if _has_pending_requests():
                                    LOGGER.info(
                                        "Se detectaron pendientes antes de cerrar Google Messages."
                                    )
                                    last_activity_at = _utc_now()
                                    continue

                                _close_sender_session(sender_session)
                                sender_session = None
                                last_activity_at = None

                        time.sleep(POLL_INTERVAL_SECONDS)
                        continue

                    LOGGER.info(
                        "Procesando solicitud Gasca SMS id=%s pin=%s phone=%s",
                        request.id,
                        request.pin_normalized,
                        request.requested_phone_masked,
                    )

                    if sender_session is None:
                        sender_session = GoogleMessagesSmsSenderSession()

                    process_gasca_sms_request(
                        request,
                        sender_session=sender_session,
                        headless=True,
                    )

                    db.session.commit()
                    last_activity_at = _utc_now()

                    LOGGER.info(
                        "Solicitud Gasca SMS id=%s finalizada con status=%s",
                        request.id,
                        request.status,
                    )

                    time.sleep(BATCH_SLEEP_SECONDS)

                except GoogleMessagesSmsSenderError:
                    LOGGER.exception(
                        "Error controlado de Google Messages procesando solicitud id=%s",
                        getattr(request, "id", None),
                    )
                    db.session.rollback()

                    # Si la sesión quedó en estado raro, se cierra para que el siguiente ciclo abra limpio.
                    _close_sender_session(sender_session)
                    sender_session = None
                    last_activity_at = None
                    time.sleep(POLL_INTERVAL_SECONDS)

                except Exception:
                    LOGGER.exception(
                        "Error inesperado procesando solicitud Gasca SMS id=%s",
                        getattr(request, "id", None),
                    )
                    db.session.rollback()

                    _close_sender_session(sender_session)
                    sender_session = None
                    last_activity_at = None
                    time.sleep(POLL_INTERVAL_SECONDS)

                finally:
                    db.session.remove()

        finally:
            _close_sender_session(sender_session)
            db.session.remove()
            LOGGER.info("Worker Gasca SMS detenido.")


if __name__ == "__main__":
    run_worker_loop()
