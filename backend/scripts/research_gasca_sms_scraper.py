from __future__ import annotations

import argparse
import json
import os
import re
from dataclasses import asdict, dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright


SMS_CODES_PATH = "/Catalogo/PaseCortesia/BuscarCodigosSms"
DATE_FORMAT = "%d-%m-%Y %H:%M:%S"


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


def load_env(env_file: str | None = None) -> Path | None:
    script_path = Path(__file__).resolve()
    backend_dir = script_path.parents[1]
    repo_root = script_path.parents[2]

    candidates: list[Path] = []

    if env_file:
        candidates.append(Path(env_file))

    candidates.extend(
        [
            backend_dir / ".env.local",
            repo_root / ".env.local",
            backend_dir / ".env.docker",
            repo_root / ".env.docker",
            backend_dir / ".env",
            repo_root / ".env",
        ]
    )

    for candidate in candidates:
        if candidate.exists():
            load_dotenv(dotenv_path=candidate, override=False)
            return candidate

    return None


def normalize_pin(pin_raw: str) -> str:
    digits = re.sub(r"\D", "", pin_raw or "")
    if not digits:
        raise ValueError("PIN vacío o inválido.")
    if len(digits) > 5:
        raise ValueError(f"PIN inválido: se esperaban máximo 5 dígitos y llegaron {len(digits)}.")
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
    return f"{phone[:3]}******{digits[-4:]}"


def mask_code(code: str) -> str:
    clean = (code or "").strip()
    if len(clean) <= 2:
        return "**"
    return clean[:2] + "*" * max(len(clean) - 2, 0)


def resolve_gasca_urls() -> tuple[str, str]:
    base = (os.getenv("GASCA_BASE_URL") or "").strip().rstrip("/")
    if not base:
        raise RuntimeError("Falta GASCA_BASE_URL en el .env.")

    if base.lower().endswith("/login"):
        root = base[: -len("/Login")]
        login_url = base
    else:
        root = base
        login_url = root + "/Login"

    codes_url = root.rstrip("/") + SMS_CODES_PATH
    return login_url, codes_url


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


def row_for_output(row: GascaSmsRow | None, *, show_sensitive: bool) -> dict[str, Any] | None:
    if row is None:
        return None

    data = asdict(row)

    if not show_sensitive:
        data["telefono"] = mask_phone(row.telefono)
        data["codigo"] = mask_code(row.codigo)
        data["nombre"] = row.nombre[:3] + "***" if row.nombre else ""

    return data


def build_result(
    *,
    pin_normalized: str,
    phone_raw: str | None,
    rows: list[GascaSmsRow],
    today: date,
    show_sensitive: bool,
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

    if not phone_raw:
        return {
            "ok": False,
            "status": "phone_required_for_contract",
            "user_message": "No se puede decidir envío: falta teléfono capturado para comparar contra Gasca.",
            "pin_normalized": pin_normalized,
            "rows_found": len(pin_rows),
            "rows": [row_for_output(row, show_sensitive=show_sensitive) for row in pin_rows],
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


def do_login(page: Any, login_url: str, user: str, password: str) -> None:
    page.goto(login_url, wait_until="domcontentloaded", timeout=60_000)

    page.get_by_label("Usuario").fill(user)
    page.get_by_label("Contraseña").fill(password)
    page.get_by_role("button", name=re.compile("INICIAR SESIÓN", re.I)).click()

    page.wait_for_load_state("networkidle", timeout=60_000)


def search_pin(page: Any, codes_url: str, pin_normalized: str) -> list[GascaSmsRow]:
    page.goto(codes_url, wait_until="domcontentloaded", timeout=60_000)

    criterio = page.locator("input#criterio")
    criterio.wait_for(state="visible", timeout=30_000)
    criterio.fill(pin_normalized)

    try:
        criterio.press("Enter")
        page.wait_for_load_state("networkidle", timeout=60_000)
    except PlaywrightTimeoutError:
        page.locator('form:has(input#criterio) button[type="submit"]').click()
        page.wait_for_load_state("networkidle", timeout=60_000)

    return parse_rows_from_page(page)


def main() -> None:
    parser = argparse.ArgumentParser(description="Investigación local: buscar códigos SMS de Gasca por PIN.")
    parser.add_argument("--pin", required=True, help="PIN recibido. Se normaliza a 5 dígitos.")
    parser.add_argument("--phone", help="Teléfono capturado en Suite para doble check.")
    parser.add_argument("--today", help="Fecha actual para pruebas, formato YYYY-MM-DD. Default: hoy local.")
    parser.add_argument("--env-file", help="Ruta explícita al .env a cargar.")
    parser.add_argument("--headful", action="store_true", help="Abrir navegador visible para depurar.")
    parser.add_argument("--show-sensitive", action="store_true", help="Mostrar teléfono, nombre y código completos en JSON local.")
    args = parser.parse_args()

    loaded_env = load_env(args.env_file)

    user = (os.getenv("GASCA_USER") or "").strip()
    password = (os.getenv("GASCA_PASS") or "").strip()

    if not user or not password:
        raise RuntimeError("Faltan GASCA_USER / GASCA_PASS en el .env.")

    login_url, codes_url = resolve_gasca_urls()
    pin_normalized = normalize_pin(args.pin)
    today = datetime.strptime(args.today, "%Y-%m-%d").date() if args.today else date.today()

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=not args.headful)
        context = browser.new_context()
        page = context.new_page()

        page.set_default_timeout(60_000)
        page.set_default_navigation_timeout(60_000)

        try:
            do_login(page, login_url, user, password)
            rows = search_pin(page, codes_url, pin_normalized)
            result = build_result(
                pin_normalized=pin_normalized,
                phone_raw=args.phone,
                rows=rows,
                today=today,
                show_sensitive=args.show_sensitive,
            )
            result["loaded_env"] = str(loaded_env) if loaded_env else None
            result["codes_url"] = codes_url
            print(json.dumps(result, ensure_ascii=False, indent=2))
        finally:
            context.close()
            browser.close()


if __name__ == "__main__":
    main()
