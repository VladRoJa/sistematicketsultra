"""Standalone Playwright worker for iVentas template creation."""

import logging
import signal
from threading import Event

from playwright.sync_api import Error as PlaywrightError, sync_playwright
from sqlalchemy import text

from app import create_app
from app.extensions import db
from app.integrations.iventas.template_browser import upload_template
from app.services.marketing_campaign_v2_dispatch_config_service import resolve_dispatch_channel_binding
from app.services.marketing_campaign_v2_template_credentials_service import (
    IventasTemplateCredentialsError,
    load_iventas_template_credentials,
)
from app.services.marketing_campaign_v2_template_upload_service import (
    claim_next_branch,
    finish_branch,
    recover_interrupted_uploads,
    template_upload_enabled,
)


LOGGER = logging.getLogger(__name__)
_LOCK_KEY = 32481560591


def _run_one(browser) -> bool:
    claim = claim_next_branch(db.session)
    if claim is None:
        return False
    upload_id, branch, template, image, image_type = claim
    branch_id = branch["sucursal_id"]

    try:
        binding = resolve_dispatch_channel_binding(sucursal_id=branch_id)
        if binding is None or binding.provider_channel_id != branch["provider_channel_id"]:
            status, detail = "ERROR", "Cambió el canal activo de la sucursal."
        else:
            login = load_iventas_template_credentials().get(branch_id)
            if login is None:
                status, detail = "ERROR", "La sucursal no tiene un acceso en el Excel."
            else:
                db.session.remove()
                status, detail = upload_template(browser, login, template, image, image_type)
    except IventasTemplateCredentialsError as error:
        status, detail = "ERROR", str(error)
    except PlaywrightError:
        # A browser failure outside the editor flow needs manual verification.
        status, detail = "VERIFY", "El navegador se interrumpió. Verifica la cuenta en iVentas."
    finally:
        db.session.remove()

    finish_branch(db.session, upload_id, branch_id, status, detail)
    db.session.remove()
    return True


def main() -> None:
    if not template_upload_enabled():
        return
    logging.basicConfig(level=logging.INFO)
    stop = Event()
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    signal.signal(signal.SIGTERM, lambda *_: stop.set())

    with create_app().app_context(), db.engine.connect().execution_options(isolation_level="AUTOCOMMIT") as lock:
        if not lock.execute(text("SELECT pg_try_advisory_lock(:key)"), {"key": _LOCK_KEY}).scalar():
            LOGGER.info("Ya hay un worker de plantillas iVentas activo.")
            return
        try:
            recover_interrupted_uploads(db.session)
            db.session.remove()
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch()
                while not stop.is_set():
                    if not _run_one(browser):
                        db.session.remove()
                        stop.wait(5)
        finally:
            lock.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": _LOCK_KEY})


if __name__ == "__main__":
    main()
