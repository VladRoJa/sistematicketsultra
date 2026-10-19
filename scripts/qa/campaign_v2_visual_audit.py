#!/usr/bin/env python3
"""Read-only Playwright audit of Suite Ultra Campaigns V2.

Anonymous mode works against a frontend-only build.
Authenticated mode supports synthetic QA, or explicitly authorized real data
on loopback-only localhost; never against a production URL.
Never exports browser storage, tokens, usernames, passwords or request bodies.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

from playwright.sync_api import TimeoutError as PlaywrightTimeout
from playwright.sync_api import sync_playwright


VIEWPORTS = {
    "desktop": (1440, 900),
    "compact": (1024, 768),
    "mobile": (390, 844),
}
CAMPAIGNS_ROUTE = "/#/marketing/campaigns-v2"
TICKET_V1_ROUTE = "/#/main/crear-ticket"
WRITE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}

# Visual measurements only; no displayed text or field values enter the report.
METRICS_JS = r"""(root) => {
  const visible = (el) => {
    const rect = el.getBoundingClientRect();
    const css = window.getComputedStyle(el);
    return rect.width > 0 && rect.height > 0 &&
      css.display !== "none" && css.visibility !== "hidden";
  };
  const fontPx = (el) => Number.parseFloat(window.getComputedStyle(el).fontSize) || 0;
  const floatScale = (el) => {
    const t = window.getComputedStyle(el).transform;
    if (!t || t === "none") return 1;
    const match = t.match(/^matrix\(([^,]+)/);
    return match ? Math.abs(Number(match[1])) : 1;
  };
  const fields = Array.from(root.querySelectorAll(".mat-mdc-form-field")).filter(visible);
  const labels = Array.from(root.querySelectorAll(".mat-mdc-floating-label")).filter(visible);
  const values = Array.from(root.querySelectorAll(".mat-mdc-select-value, input.mat-mdc-input-element")).filter(visible);
  const smallLabels = labels.filter(el => fontPx(el) * floatScale(el) < 9.5);
  const smallValues = values.filter(el => fontPx(el) < 12);
  const clipped = Array.from(root.querySelectorAll("input.mat-mdc-input-element"))
    .filter(visible)
    .filter(el => {
      const content = el.value || el.placeholder || "";
      if (!content) return false;
      const style = window.getComputedStyle(el);
      const ctx = document.createElement("canvas").getContext("2d");
      if (!ctx) return false;
      ctx.font = style.font;
      const free = el.clientWidth - (parseFloat(style.paddingLeft) || 0) -
        (parseFloat(style.paddingRight) || 0) - 6;
      return ctx.measureText(content).width > free + 2;
    });
  return {
    fields: fields.length,
    visible_labels: labels.length,
    tiny_labels: smallLabels.length,
    visible_values: values.length,
    tiny_values: smallValues.length,
    clipped_inputs: clipped.length,
    horizontal_overflow_px: Math.max(0, root.scrollWidth - root.clientWidth),
  };
}"""


def calibrate_detector(page) -> None:
    """Confirm that tiny labels/values and truncated inputs are detectable."""
    page.set_content("""
      <div id="metric-probe">
        <div class="mat-mdc-form-field">
          <span class="mat-mdc-floating-label" style="font-size:8px">Tiny label</span>
          <div class="mat-mdc-select-value" style="font-size:10px">Tiny value</div>
          <input class="mat-mdc-input-element"
                 style="display:block;width:65px;font-size:10px"
                 value="THIS IS A LONG SYNTHETIC CAMPAIGN NAME">
        </div>
      </div>
    """)
    result = page.locator("#metric-probe").evaluate(METRICS_JS)
    if not all(result[key] > 0 for key in ("tiny_labels", "tiny_values", "clipped_inputs")):
        raise RuntimeError("Visual metric calibration failed")


def validate_target(mode: str, base: str) -> None:
    parsed = urlparse(base)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("SUITE_QA_BASE_URL must be an HTTP(S) URL")
    host = parsed.hostname.lower()
    local = host in {"localhost", "127.0.0.1", "::1"}
    if not local and parsed.scheme != "https":
        raise ValueError("Remote QA audit requires HTTPS")
    if mode == "authenticated":
        synthetic_qa = os.getenv("SUITE_QA_SYNTHETIC_DATA_CONFIRMED") == "YES"
        real_local = os.getenv("SUITE_QA_REAL_LOCAL_READONLY_CONFIRMED") == "YES"
        if synthetic_qa == real_local:
            raise ValueError("Choose exactly one data mode: synthetic QA OR real local read-only")
        if real_local and not local:
            raise ValueError("Real-data audit is permitted only on localhost / 127.0.0.1 / ::1")
        if os.getenv("SUITE_QA_ALLOWED_HOST", "").lower() != host:
            raise ValueError("Set SUITE_QA_ALLOWED_HOST to the exact audit hostname")
        if not os.getenv("SUITE_QA_USERNAME") or not os.getenv("SUITE_QA_PASSWORD"):
            raise ValueError("Audit credentials missing (provide via environment, not CLI)")


def navigate(page, base: str, route: str) -> None:
    page.goto(base.rstrip("/") + route, wait_until="domcontentloaded", timeout=30000)


def record_case(page, output: Path, viewport: str, name: str, root_selector: str,
                failures: list[str], cases: list[dict], reference: bool = False) -> None:
    root = page.locator(root_selector).first
    try:
        root.wait_for(state="visible", timeout=12000)
        root.scroll_into_view_if_needed(timeout=5000)
        page.wait_for_timeout(250)
        metrics = root.evaluate(METRICS_JS)
        screenshot = f"{viewport}-{name}.png"
        page.screenshot(path=str(output / screenshot), full_page=False, animations="disabled")
        # V1 is a visual reference, not subject to new Campaign V2 thresholds.
        issues = [] if reference else [
            key for key in ("tiny_labels", "tiny_values", "clipped_inputs")
            if metrics[key] > 0
        ]
        status = "FAIL_VISUAL" if issues else "PASS"
        cases.append({"viewport": viewport, "case": name, "status": status,
                      "screenshot": screenshot, "measurements": metrics, "issues": issues})
        if issues:
            failures.append(f"{viewport}/{name}: {','.join(issues)}")
    except (PlaywrightTimeout, Exception) as exc:
        # Do not dump page HTML, server errors, or request details to artifacts.
        cases.append({"viewport": viewport, "case": name, "status": "BLOCKED",
                      "reason": type(exc).__name__})
        failures.append(f"{viewport}/{name}: BLOCKED")


def authenticate(page, base: str) -> None:
    navigate(page, base, "/#/login")
    page.locator("#usuario-login").wait_for(state="visible", timeout=15000)
    page.locator("#usuario-login").fill(os.environ["SUITE_QA_USERNAME"])
    page.locator("#password-login").fill(os.environ["SUITE_QA_PASSWORD"])
    page.get_by_role("button", name="Iniciar sesión").click()
    # The login component stores a JWT through SessionService; only test
    # its existence in-page. Never return or persist the token.
    page.wait_for_function("Boolean(window.localStorage.getItem('token'))", timeout=20000)


def close_dialog(page) -> None:
    page.keyboard.press("Escape")
    try:
        page.locator("mat-dialog-container").wait_for(state="hidden", timeout=2500)
    except PlaywrightTimeout:
        close = page.locator("mat-dialog-container").get_by_role("button", name="Cerrar")
        if close.count():
            close.first.click()
        page.locator("mat-dialog-container").wait_for(state="hidden", timeout=3500)


class AuditNavigationTimeout(RuntimeError):
    """Safe diagnostic stage; never include element text or Playwright details."""


def open_tool(page, label: str) -> None:
    try:
        page.get_by_role(
            "button", name="Abrir herramientas de campañas", exact=True
        ).click(timeout=6000)
    except PlaywrightTimeout as exc:
        raise AuditNavigationTimeout("tools_trigger_click_timeout") from exc
    try:
        page.get_by_role("menuitem", name=label, exact=True).click(timeout=6000)
    except PlaywrightTimeout as exc:
        raise AuditNavigationTimeout("tools_menu_item_click_timeout") from exc


def audit_authenticated(page, output: Path, viewport: str,
                        failures: list[str], cases: list[dict], base: str) -> None:
    authenticate(page, base)
    navigate(page, base, TICKET_V1_ROUTE)
    record_case(page, output, viewport, "ticket-v1-reference",
                ".crear-ticket-page", failures, cases, reference=True)

    navigate(page, base, CAMPAIGNS_ROUTE)
    page.locator("#campaign-v2-builder").wait_for(state="visible", timeout=25000)
    if page.locator(".access-panel").count():
        raise RuntimeError("QA account lacks Campaigns V2 access")
    record_case(page, output, viewport, "campaign-builder",
                "section.workspace.builder", failures, cases)
    record_case(page, output, viewport, "campaign-results",
                "section.reporting-workspace", failures, cases)
    record_case(page, output, viewport, "campaign-history",
                'section.workspace[aria-labelledby="campaign-v2-history"]', failures, cases)

    def dialog_case(name: str, opener) -> None:
        try:
            opener()
            try:
                page.locator("mat-dialog-container").wait_for(state="visible", timeout=10000)
            except PlaywrightTimeout as exc:
                raise AuditNavigationTimeout("dialog_visibility_timeout") from exc
            record_case(page, output, viewport, name, "mat-dialog-container",
                        failures, cases)
        except Exception as exc:
            safe_reason = (str(exc) if isinstance(exc, AuditNavigationTimeout)
                           else type(exc).__name__)
            cases.append({"viewport": viewport, "case": name, "status": "BLOCKED",
                          "reason": safe_reason})
            failures.append(f"{viewport}/{name}: BLOCKED")
        finally:
            if page.locator("mat-dialog-container").count():
                close_dialog(page)

    dialog_case("excel", lambda: page.get_by_role("button", name="Crear desde Excel/CSV").click())
    tools = [
        ("qa-manual", "Preparar prueba interna · 1 contacto"),
        ("channel-status", "Estado de los canales"),
        ("dispatch-config", "Plantillas, canales y tarifas"),
        ("send-limits", "Límites de envío"),
    ]
    for key, label in tools:
        dialog_case(key, lambda label=label: open_tool(page, label))

    # History detail requires a synthetic, pre-seeded campaign.
    detail = page.locator('section.workspace[aria-labelledby="campaign-v2-history"] tbody tr').first
    if detail.count():
        dialog_case("campaign-detail", lambda: detail.get_by_role("button", name="Ver detalle").click())
    else:
        cases.append({"viewport": viewport, "case": "campaign-detail",
                      "status": "BLOCKED", "reason": "no_synthetic_campaign_seed"})
        failures.append(f"{viewport}/campaign-detail: BLOCKED")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("anonymous", "authenticated"), required=True)
    parser.add_argument("--base-url", default=os.getenv("SUITE_QA_BASE_URL", "http://127.0.0.1:4173"))
    parser.add_argument("--out", default="artifacts/campaign-v2-visual")
    args = parser.parse_args()
    try:
        validate_target(args.mode, args.base_url)
    except ValueError as exc:
        print(f"CONFIG_ERROR: {exc}", file=sys.stderr)
        return 2
    output = Path(args.out)
    output.mkdir(parents=True, exist_ok=True)
    failures, cases = [], []
    blocked_writes = [0]
    blocked_external_api = [0]
    primary = urlparse(args.base_url)
    allowed_api_origins = {f"{primary.scheme}://{primary.netloc.lower()}"}
    extra_api_origin = os.getenv("SUITE_QA_ALLOWED_API_ORIGIN", "").rstrip("/")
    if extra_api_origin:
        api = urlparse(extra_api_origin)
        if not api.hostname or (api.scheme != "https" and
                api.hostname.lower() not in {"127.0.0.1", "localhost", "::1"}):
            print("CONFIG_ERROR: API origin must be HTTPS or local", file=sys.stderr)
            return 2
        if os.getenv("SUITE_QA_REAL_LOCAL_READONLY_CONFIRMED") == "YES" and (
                api.hostname.lower() not in {"localhost", "127.0.0.1", "::1"}):
            print("CONFIG_ERROR: Real local audit forbids non-loopback API hosts", file=sys.stderr)
            return 2
        allowed_api_origins.add(f"{api.scheme}://{api.netloc.lower()}")
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            for name, (width, height) in VIEWPORTS.items():
                context = browser.new_context(viewport={"width": width, "height": height},
                                              device_scale_factor=1, reduced_motion="reduce")
                def readonly(route):
                    url = urlparse(route.request.url)
                    origin = f"{url.scheme}://{url.netloc.lower()}"
                    if url.path.startswith("/api/") and origin not in allowed_api_origins:
                        blocked_external_api[0] += 1
                        return route.abort("blockedbyclient")
                    if route.request.method.upper() in WRITE_METHODS:
                        login = url.path.rstrip("/").endswith("/api/auth/login")
                        if args.mode == "authenticated" and login:
                            return route.continue_()
                        blocked_writes[0] += 1
                        return route.abort("blockedbyclient")
                    return route.continue_()
                context.route("**/*", readonly)
                page = context.new_page()
                try:
                    if name == "desktop":
                        calibrate_detector(page)
                        cases.append({"viewport": name, "case": "detector-calibration",
                                      "status": "PASS"})
                    if args.mode == "anonymous":
                        navigate(page, args.base_url, CAMPAIGNS_ROUTE)
                        page.locator("#usuario-login").wait_for(state="visible", timeout=20000)
                        screenshot = f"{name}-anonymous-login.png"
                        page.screenshot(path=str(output / screenshot), animations="disabled")
                        cases.append({"viewport": name, "case": "auth-guard",
                                      "status": "PASS", "screenshot": screenshot})
                    else:
                        audit_authenticated(page, output, name, failures, cases, args.base_url)
                except Exception as exc:
                    cases.append({"viewport": name, "case": "navigation",
                                  "status": "BLOCKED", "reason": type(exc).__name__})
                    failures.append(f"{name}/navigation: BLOCKED")
                finally:
                    context.close()
        finally:
            browser.close()
    if blocked_writes[0]:
        failures.append("Unexpected write requests blocked by the browser")
    if blocked_external_api[0]:
        failures.append("Unapproved API origin blocked by the browser")
    report = {
        "mode": args.mode,
        "viewports": list(VIEWPORTS),
        "cases": cases,
        "blocked_write_requests": blocked_writes[0],
        "blocked_external_api_requests": blocked_external_api[0],
        "summary": {
            "pass": sum(x["status"] == "PASS" for x in cases),
            "fail_visual": sum(x["status"] == "FAIL_VISUAL" for x in cases),
            "blocked": sum(x["status"] == "BLOCKED" for x in cases),
        },
    }
    (output / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report["summary"], sort_keys=True))
    # Fail closed: blocked evidence cannot be misrepresented as visual QA PASS.
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
