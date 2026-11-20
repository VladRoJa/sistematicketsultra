"""Read the worker-only iVentas login workbook and resolve its Suite branches."""

from __future__ import annotations

import os
from dataclasses import dataclass, field

from openpyxl import load_workbook
from openpyxl.workbook import Workbook

from app.services.marketing_campaign_v2_dispatch_branch_service import (
    CampaignV2DispatchBranchResolver,
)
from app.warehouse.services.socios_vencidos_current_status_resolver import (
    normalize_socios_vencidos_branch_key,
)


CREDENTIALS_FILE_ENV = "IVENTAS_TEMPLATE_CREDENTIALS_FILE"
_REQUIRED_HEADERS = ("SUCURSAL", "CORREO", "CONTRASENA")


class IventasTemplateCredentialsError(ValueError):
    """The workbook cannot be used to look up a unique branch login."""


@dataclass(frozen=True, slots=True)
class IventasTemplateCredentials:
    email: str = field(repr=False)
    password: str = field(repr=False)


def load_iventas_template_credentials(*, session=None) -> dict[int, IventasTemplateCredentials]:
    """Return the credentials keyed by canonical Suite branch ID."""
    path = os.environ.get(CREDENTIALS_FILE_ENV, "").strip()
    if not path:
        raise IventasTemplateCredentialsError(f"Falta configurar {CREDENTIALS_FILE_ENV}.")

    resolver = CampaignV2DispatchBranchResolver(session=session)
    credentials: dict[int, IventasTemplateCredentials] = {}
    for row_number, branch_label, login in _read_workbook(path):
        branch = resolver.resolve(branch_label)
        if branch is None:
            raise IventasTemplateCredentialsError(
                f"Fila {row_number}: la sucursal no coincide con una sucursal activa única."
            )
        if branch.sucursal_id in credentials:
            raise IventasTemplateCredentialsError(
                f"Fila {row_number}: la sucursal ya tiene una fila de credenciales."
            )
        credentials[branch.sucursal_id] = login

    return credentials


def _read_workbook(path: str) -> list[tuple[int, str, IventasTemplateCredentials]]:
    try:
        workbook = load_workbook(path, read_only=True, data_only=True, keep_links=False)
        try:
            return _read_credentials_sheet(workbook)
        finally:
            workbook.close()
    except IventasTemplateCredentialsError:
        raise
    except Exception:
        raise IventasTemplateCredentialsError(
            "No fue posible leer el Excel de accesos de iVentas."
        ) from None


def _read_credentials_sheet(workbook: Workbook) -> list[tuple[int, str, IventasTemplateCredentials]]:
    matching_sheets = []
    for sheet in workbook.worksheets:
        first_row = next(sheet.iter_rows(min_row=1, max_row=1, values_only=True), ())
        headers = tuple(normalize_socios_vencidos_branch_key(cell) for cell in first_row)
        if all(header in headers for header in _REQUIRED_HEADERS):
            matching_sheets.append((sheet, headers))

    if not matching_sheets:
        raise IventasTemplateCredentialsError(
            "La primera fila debe incluir las columnas sucursal, correo y contraseña."
        )
    if len(matching_sheets) != 1:
        raise IventasTemplateCredentialsError(
            "El Excel contiene más de una pestaña con las columnas de accesos."
        )

    sheet, headers = matching_sheets[0]
    if any(headers.count(header) != 1 for header in _REQUIRED_HEADERS):
        raise IventasTemplateCredentialsError("El Excel repite una columna de accesos.")

    branch_column, email_column, password_column = (
        headers.index(header) for header in _REQUIRED_HEADERS
    )
    rows = sheet.iter_rows(min_row=2, max_col=len(headers), values_only=True)
    credentials = []
    for row_number, row in enumerate(rows, start=2):
        branch, email, password = row[branch_column], row[email_column], row[password_column]
        values = (branch, email, password)
        if all(value in (None, "") for value in values):
            continue
        if not all(isinstance(value, str) and value.strip() for value in values):
            raise IventasTemplateCredentialsError(
                f"Fila {row_number}: sucursal, correo y contraseña deben contener texto."
            )
        login = IventasTemplateCredentials(email=email.strip(), password=password)
        credentials.append((row_number, branch.strip(), login))

    if not credentials:
        raise IventasTemplateCredentialsError("El Excel de accesos no tiene filas de sucursal.")
    return credentials
