"""Standalone Playwright worker for iVentas template creation."""

import logging
import signal
from threading import Event

from playwright.sync_api import Error as PlaywrightError, sync_playwright
from sqlalchemy import text

from app import create_app
from app.extensions import db
from app.integrations.iventas.template_browser import read_template_approval, upload_template
from app.services.marketing_campaign_v2_dispatch_config_service import resolve_dispatch_channel_binding
from app.services.marketing_campaign_v2_template_credentials_service import (
    IventasTemplateCredentialsError,
    load_iventas_template_credentials,
)
from app.services.marketing_campaign_v2_template_upload_service import (
    IN_REVIEW,
    claim_due_review,
    claim_next_branch,
    finish_branch,
    finish_review,
    recover_interrupted_uploads,
    template_upload_enabled,
)


LOGGER = logging.getLogger(__name__)
_LOCK_KEY = 32481560591


def _branch_login(branch):
    branch_id = branch["sucursal_id"]
    binding = resolve_dispatch_channel_binding(sucursal_id=branch_id)
    if binding is None or binding.provider_channel_id != branch["provider_channel_id"]:
        return None, "Cambió el canal activo de la sucursal."
    db.session.remove()
    login = load_iventas_template_credentials().get(branch_id)
    return (login, "") if login else (None, "La sucursal no tiene un acceso en el Excel.")


def _run_one(browser) -> bool:
    claim = claim_next_branch(db.session)
    if claim is None:
        return False
    upload_id, branch, template, image, image_type = claim
    branch_id = branch["sucursal_id"]

    try:
        login, detail = _branch_login(branch)
        status, detail = upload_template(browser, login, template, image, image_type) if login else ("ERROR", detail)
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


def _review_one(browser) -> bool:
    claim = claim_due_review(db.session)
    if claim is None:
        return False
    upload_id, branch, template = claim
    try:
        login, detail = _branch_login(branch)
        if login:
            status, detail = read_template_approval(browser, login, template, branch["provider_channel_id"])
        else:
            status = IN_REVIEW
    except IventasTemplateCredentialsError as error:
        status, detail = IN_REVIEW, str(error)
    except PlaywrightError:
        status, detail = IN_REVIEW, "No se pudo verificar el estado. La Suite volverá a consultar iVentas."
    finally:
        db.session.remove()

    finish_review(db.session, upload_id, branch["sucursal_id"], status, detail)
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
                    uploaded = _run_one(browser)
                    reviewed = not stop.is_set() and _review_one(browser)
                    if not (uploaded or reviewed):
                        db.session.remove()
                        stop.wait(5)
        finally:
            lock.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": _LOCK_KEY})


if __name__ == "__main__":
    main()
