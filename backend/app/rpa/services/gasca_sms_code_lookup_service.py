from __future__ import annotations

import os
import re
from dataclasses import asdict, dataclass
from datetime import date, datetime
from typing import Any

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright


SMS_CODES_PATH = "/Catalogo/PaseCortesia/BuscarCodigosSms"
DATE_FORMAT = "%d-%m-%Y %H:%M:%S"


class GascaSmsCodeLookupError(RuntimeError):
    pass


@dataclass(frozen=True)
class GascaSmsLookupConfig:
    base_url: str
    user: str
    password: str
    headless: bool = True
    timeout_ms: int = 60_000


@dataclass
class GascaSmsRow:
    pin: str
    nombre: str
    telefono: str
    codigo: str
    generado: str
    utilizado: str
    sucursal: str

    @property
    def generado_dt(self) -> datetime | None:
        try:
            return datetime.strptime(self.generado, DATE_FORMAT)
        except ValueError:
            return None

    @property
    def utilizado_dt(self) -> datetime | None:
        if not self.utilizado:
            return None
        try:
            return datetime.strptime(self.utilizado, DATE_FORMAT)
        except ValueError:
            return None


def resolve_config_from_env(*, headless: bool = True) -> GascaSmsLookupConfig:
    base_url = (os.getenv("GASCA_BASE_URL") or "").strip()
    user = (os.getenv("GASCA_USER") or "").strip()
    password = (os.getenv("GASCA_PASS") or "").strip()

    missing: list[str] = []
    if not base_url:
        missing.append("GASCA_BASE_URL")
    if not user:
        missing.append("GASCA_USER")
    if not password:
        missing.append("GASCA_PASS")

    if missing:
        raise GascaSmsCodeLookupError(
            "Faltan variables de entorno para Gasca SMS: " + ", ".join(missing)
        )

    return GascaSmsLookupConfig(
        base_url=base_url,
        user=user,
        password=password,
        headless=headless,
    )


def normalize_pin(pin_raw: str) -> str:
    digits = re.sub(r"\D", "", pin_raw or "")
    if not digits:
        raise ValueError("PIN vacío o inválido.")
    if len(digits) > 5:
        raise ValueError(
            f"PIN inválido: se esperaban máximo 5 dígitos y llegaron {len(digits)}."
        )
    return digits.zfill(5)


def phone_digits(phone: str) -> str:
    digits = re.sub(r"\D", "", phone or "")
    if digits.startswith("00"):
        digits = digits[2:]
    return digits


def phones_match(input_phone: str, gasca_phone: str) -> tuple[bool, str]:
    input_digits = phone_digits(input_phone)
    gasca_digits = phone_digits(gasca_phone)

    if not input_digits or not gasca_digits:
        return False, "empty"

    if input_digits == gasca_digits:
        return True, "exact_digits"

    if len(input_digits) >= 10 and len(gasca_digits) >= 10:
        if input_digits[-10:] == gasca_digits[-10:]:
            return True, "last_10_digits"

    return False, "no_match"


def mask_phone(phone: str) -> str:
    digits = phone_digits(phone)
    if len(digits) <= 4:
        return "****"

    prefix = ""
    clean = (phone or "").strip()
    if clean.startswith("+"):
        prefix = clean[:3]

    return f"{prefix}******{digits[-4:]}"


def mask_code(code: str) -> str:
    clean = (code or "").strip()
    if len(clean) <= 2:
        return "**"
    return clean[:2] + "*" * max(len(clean) - 2, 0)


def resolve_gasca_urls(config: GascaSmsLookupConfig) -> tuple[str, str]:
    base = config.base_url.strip().rstrip("/")
    if not base:
        raise GascaSmsCodeLookupError("GASCA_BASE_URL está vacío.")

    if base.lower().endswith("/login"):
        root = base[: -len("/Login")]
        login_url = base
    else:
        root = base
        login_url = root + "/Login"

    codes_url = root.rstrip("/") + SMS_CODES_PATH
    return login_url, codes_url


def row_for_output(row: GascaSmsRow | None, *, show_sensitive: bool = False) -> dict[str, Any] | None:
    if row is None:
        return None

    data = asdict(row)

    if not show_sensitive:
        data["telefono"] = mask_phone(row.telefono)
        data["codigo"] = mask_code(row.codigo)
        data["nombre"] = row.nombre[:3] + "***" if row.nombre else ""

    return data


def build_lookup_result(
    *,
    pin_normalized: str,
    phone_raw: str,
    rows: list[GascaSmsRow],
    today: date,
    show_sensitive: bool = False,
) -> dict[str, Any]:
    pin_rows = [row for row in rows if row.pin == pin_normalized]

    if not pin_rows:
        return {
            "ok": False,
            "status": "code_not_found",
            "user_message": "No se envió SMS. No se encontró ningún registro en Gasca para ese PIN.",
            "pin_normalized": pin_normalized,
            "rows_found": 0,
        }

    phone_matches: list[tuple[GascaSmsRow, str]] = []
    for row in pin_rows:
        matches, mode = phones_match(phone_raw, row.telefono)
        if matches:
            phone_matches.append((row, mode))

    if not phone_matches:
        return {
            "ok": False,
            "status": "phone_not_found_for_pin",
            "user_message": "No se envió SMS. El teléfono capturado no coincide con ningún teléfono encontrado en Gasca para ese PIN.",
            "pin_normalized": pin_normalized,
            "phone_input_masked": mask_phone(phone_raw),
            "rows_found": len(pin_rows),
            "gasca_phones": [mask_phone(row.telefono) for row in pin_rows],
        }

    matched_rows = [row for row, _mode in phone_matches]
    today_rows = [
        row
        for row in matched_rows
        if row.generado_dt is not None and row.generado_dt.date() == today
    ]

    if not today_rows:
        newest = max(
            (row for row in matched_rows if row.generado_dt is not None),
            key=lambda row: row.generado_dt,
            default=matched_rows[0],
        )
        return {
            "ok": False,
            "status": "code_not_generated_today",
            "user_message": "No se envió SMS. Se encontró registro para el PIN y teléfono, pero el código no fue generado hoy.",
            "pin_normalized": pin_normalized,
            "selected": row_for_output(newest, show_sensitive=show_sensitive),
            "today": today.isoformat(),
        }

    unused_today_rows = [row for row in today_rows if not row.utilizado.strip()]

    if not unused_today_rows:
        newest_today = max(
            (row for row in today_rows if row.generado_dt is not None),
            key=lambda row: row.generado_dt,
            default=today_rows[0],
        )
        return {
            "ok": False,
            "status": "code_already_used",
            "user_message": "No se envió SMS. El código encontrado ya aparece como utilizado en Gasca.",
            "pin_normalized": pin_normalized,
            "selected": row_for_output(newest_today, show_sensitive=show_sensitive),
        }

    selected = max(
        (row for row in unused_today_rows if row.generado_dt is not None),
        key=lambda row: row.generado_dt,
        default=unused_today_rows[0],
    )

    status = "ready_to_send"
    if len(unused_today_rows) > 1:
        status = "multiple_candidates_selected_latest"

    return {
        "ok": True,
        "status": status,
        "user_message": "Código vigente encontrado. Listo para enviar SMS.",
        "pin_normalized": pin_normalized,
        "selected": row_for_output(selected, show_sensitive=show_sensitive),
        "valid_candidates": len(unused_today_rows),
    }


def parse_rows_from_page(page: Any) -> list[GascaSmsRow]:
    rows = page.evaluate(
        """
        () => {
          const allRows = [...document.querySelectorAll('table tbody tr')].map(tr =>
            [...tr.querySelectorAll('td')].map(td => td.innerText.trim())
          );

          return allRows
            .filter(cols => cols.length >= 7)
            .filter(cols => /^\\d{5}$/.test(cols[0]))
            .map(cols => ({
              pin: cols[0],
              nombre: cols[1],
              telefono: cols[2],
              codigo: cols[3],
              generado: cols[4],
              utilizado: cols[5],
              sucursal: cols[6],
            }));
        }
        """
    )

    return [GascaSmsRow(**row) for row in rows]


def do_login(page: Any, *, login_url: str, config: GascaSmsLookupConfig) -> None:
    page.goto(login_url, wait_until="domcontentloaded", timeout=config.timeout_ms)

    page.get_by_label("Usuario").fill(config.user)
    page.get_by_label("Contraseña").fill(config.password)
    page.get_by_role("button", name=re.compile("INICIAR SESIÓN", re.I)).click()

    page.wait_for_load_state("networkidle", timeout=config.timeout_ms)


def search_pin_rows(
    page: Any,
    *,
    codes_url: str,
    pin_normalized: str,
    timeout_ms: int,
) -> list[GascaSmsRow]:
    page.goto(codes_url, wait_until="domcontentloaded", timeout=timeout_ms)

    criterio = page.locator("input#criterio")
    criterio.wait_for(state="visible", timeout=timeout_ms)
    criterio.fill(pin_normalized)

    try:
        criterio.press("Enter")
        page.wait_for_load_state("networkidle", timeout=timeout_ms)
    except PlaywrightTimeoutError:
        page.locator('form:has(input#criterio) button[type="submit"]').click()
        page.wait_for_load_state("networkidle", timeout=timeout_ms)

    return parse_rows_from_page(page)


def lookup_gasca_sms_code(
    *,
    pin_raw: str,
    phone_raw: str,
    config: GascaSmsLookupConfig | None = None,
    today: date | None = None,
    show_sensitive: bool = False,
) -> dict[str, Any]:
    runtime = config or resolve_config_from_env()
    lookup_today = today or date.today()
    pin_normalized = normalize_pin(pin_raw)
    login_url, codes_url = resolve_gasca_urls(runtime)

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=runtime.headless)
        context = browser.new_context()
        page = context.new_page()

        page.set_default_timeout(runtime.timeout_ms)
        page.set_default_navigation_timeout(runtime.timeout_ms)

        try:
            do_login(page, login_url=login_url, config=runtime)
            rows = search_pin_rows(
                page,
                codes_url=codes_url,
                pin_normalized=pin_normalized,
                timeout_ms=runtime.timeout_ms,
            )

            result = build_lookup_result(
                pin_normalized=pin_normalized,
                phone_raw=phone_raw,
                rows=rows,
                today=lookup_today,
                show_sensitive=show_sensitive,
            )
            result["codes_url"] = codes_url
            return result
        finally:
            context.close()
            browser.close()
