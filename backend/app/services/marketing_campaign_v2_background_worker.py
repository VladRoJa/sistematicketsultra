"""Dedicated opt-in Campaign V2 background worker.

Never started by the Flask web application or scheduler. Installing the module
does not enable jobs. A separate, approved worker deployment is required.
"""
from __future__ import annotations

import logging
import os
import signal
import time
from uuid import uuid4

from app import create_app
from app.extensions import db
from app.integrations.iventas.broadcast_provider import IVentasBroadcastProvider
from app.services.marketing_campaign_v2_background_worker_service import (
    claim_next_queued, expire_stale_running, process_claimed_job,
    _enabled,
)

LOG = logging.getLogger(__name__)
STOP = False


def _signal_stop(*_args):
    global STOP
    STOP = True


def _provider_factory(app):
    return IVentasBroadcastProvider(
        api_key=app.config.get("IVENTAS_CAMPAIGN_SEND_API_KEY", ""),
        base_url=app.config.get(
            "IVENTAS_CAMPAIGN_SEND_API_BASE_URL", "https://rest.iventas.mx"),
    )


def run_loop(*, app, poll_seconds: int = 5) -> None:
    if type(poll_seconds) is not int or not 2 <= poll_seconds <= 60:
        raise ValueError("Intervalo inválido.")
    identity = uuid4().hex
    LOG.info("Background dispatch worker ready (id=%s)", identity)
    while not STOP:
        try:
            if _enabled(app.config):
                expire_stale_running(session=db.session)
                claim = claim_next_queued(
                    session=db.session, worker_id=identity, config=app.config,
                )
                if claim is not None:
                    job_id, generation = claim
                    process_claimed_job(
                        session=db.session, job_id=job_id, worker_id=identity,
                        generation=generation, config=app.config,
                        provider_factory=lambda: _provider_factory(app),
                        should_terminate=lambda: STOP,
                    )
        except Exception as exc:
            db.session.rollback()
            # Avoid logging provider payloads, recipient PII or credentials.
            LOG.error("Background dispatch cycle blocked: %s", type(exc).__name__)
        finally:
            db.session.remove()
        if not STOP:
            time.sleep(poll_seconds)
    LOG.info("Background dispatch worker stopped")


def main():
    signal.signal(signal.SIGTERM, _signal_stop)
    signal.signal(signal.SIGINT, _signal_stop)
    app = create_app()
    with app.app_context():
        run_loop(app=app, poll_seconds=int(os.getenv("CAMPAIGN_V2_BG_POLL_SECONDS", "5")))


if __name__ == "__main__":
    main()
