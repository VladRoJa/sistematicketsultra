#!/usr/bin/env python3
"""Gate A visual journey for background dispatch with entirely mocked HTTP.

Loopback-only Angular build, synthetic browser JWT and data, API interception.
No backend, iVentas, real identities, recipient data or POST requests.
"""
from __future__ import annotations

import argparse
import json
from urllib.parse import urlparse

from playwright.sync_api import sync_playwright

FAKE_CAMPAIGN = 90099
FAKE_JOB = 88077


def run(base: str):
    parsed = urlparse(base)
    if parsed.scheme != "http" or parsed.hostname not in ("localhost", "127.0.0.1"):
        raise ValueError("Gate A browser QA is loopback-only")
    base = base.rstrip("/")
    observed = []
    job = {
        "job_id": FAKE_JOB,
        "campaign_id": FAKE_CAMPAIGN,
        "execution_id": 19000,
        "status": "RUNNING",
        "total_pending_at_start": 26,
        "accepted_by_provider": 7,
        "current_child_id": 8,
        "stop_requested": False,
        "reason_code": None,
        "started_at": "2026-10-26T17:00:00Z",
        "finished_at": None,
        "updated_at": "2026-10-26T17:01:00Z",
        "delivery_confirmed": False,
        "may_auto_retry": False,
        "may_auto_resume": False,
    }

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1280, "height": 900})
        # JWT structure is synthetic; this test never performs a real login.
        # Only the local AuthGuard date check reads its exp claim.
        context.add_init_script(script="""(() => {
            const base64 = obj => btoa(JSON.stringify(obj))
              .replace(/=/g, '').replace(/\\+/g, '-').replace(/\\//g, '_');
            const header = base64({alg: 'HS256', typ: 'JWT'});
            const payload = base64({sub: '47', exp: 4102444800});
            localStorage.setItem('token', header + '.' + payload + '.synthetic');
            if (!localStorage.getItem('user')) {
              localStorage.setItem('user', JSON.stringify({
                id: 47, username: 'GATE_A_MKT_SYNTHETIC',
                rol: 'MARKETING', sucursal_id: 1000
              }));
            }
        })();""")

        def api_stub(route):
            request = route.request
            path = urlparse(request.url).path
            observed.append((request.method, path))
            if request.method == "GET" and path.endswith(
                "/marketing/campaigns-v2/dispatch/jobs/mine"
            ):
                route.fulfill(
                    status=200, content_type="application/json",
                    body=json.dumps({
                        "jobs": [job],
                        "background_dispatch_available": False,
                    }))
            elif request.method == "GET" and path.endswith(
                f"/marketing/campaigns-v2/{FAKE_CAMPAIGN}/dispatch/jobs/{FAKE_JOB}"
            ):
                route.fulfill(status=200, content_type="application/json",
                              body=json.dumps(job))
            else:
                # Never let an API request escape to a real backend.
                route.fulfill(status=404, content_type="application/json",
                              body='{"error":"synthetic-not-available"}')

        context.route("**/api/**", api_stub)
        page = context.new_page()
        page.goto(base + "/#/main/crear-ticket", wait_until="domcontentloaded")
        dock = page.locator(".dispatch-dock")
        dock.wait_for(state="visible", timeout=25000)
        assert "7/26 lotes aceptados" in dock.inner_text()
        assert "Campaña #90099" in dock.inner_text()
        assert "entregado" in dock.inner_text()
        assert dock.get_by_role("progressbar").get_attribute("aria-valuenow") == "7"

        dock.get_by_role("button", name="Ver detalles").click()
        dialog = page.locator("mat-dialog-container")
        dialog.wait_for(state="visible", timeout=15000)
        dialog.get_by_role("button", name="Minimizar").wait_for(
            state="visible", timeout=15000)
        dialog.get_by_role("button", name="Minimizar").click()
        dialog.wait_for(state="detached", timeout=10000)
        dock.wait_for(state="visible", timeout=10000)

        # Navigation and hard refresh must read the same server-owned job via GET.
        page.goto(base + "/#/main/ver-tickets", wait_until="domcontentloaded")
        dock.wait_for(state="visible", timeout=15000)
        page.reload(wait_until="domcontentloaded")
        dock.wait_for(state="visible", timeout=15000)
        assert "7/26 lotes aceptados" in dock.inner_text()

        # Same-tab identity replacement cannot leave the prior actor's dock visible.
        page.evaluate("""() => localStorage.setItem('user', JSON.stringify({
            id: 48, username: 'OTHER_SYNTHETIC_ACCOUNT',
            rol: 'MARKETING', sucursal_id: 1000
        }))""")
        dock.wait_for(state="detached", timeout=17000)

        write_requests = [(method, path) for method, path in observed
                          if method in ("POST", "PUT", "PATCH", "DELETE")
                          and ("/dispatch/" in path or "iventas" in path.lower())]
        assert not write_requests, "Gate A browser journey must never POST dispatch"
        assert sum(path.endswith("/dispatch/jobs/mine")
                   for _, path in observed) >= 2, "server-owned recovery was not exercised"
        print("GATE_A_BROWSER_PASS: dock, minimize, route, reload, identity-change, GET-only")
        context.close()
        browser.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True)
    opts = parser.parse_args()
    run(opts.base_url)


if __name__ == "__main__":
    main()
