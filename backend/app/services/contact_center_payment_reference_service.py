"""Validated, versioned offline member-ID evidence for Contact Center.

Never commit raw source data to Git or use this CSV to infer current membership.
"""
from __future__ import annotations

import csv
import hashlib
import os
import re
import shutil
import unicodedata
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from sqlalchemy import insert, update

from app.extensions import db
from app.models.contact_center import (
    ContactCenterPaymentReferenceBatchORM,
    ContactCenterPaymentReferenceRowORM,
)


REQUIRED_HEADERS = ("ID Socio", "Nombre", "PIN", "Sucursal", "Estado")
VALID_STATES = frozenset({"Activo", "Vencido"})
CHUNK_SIZE = 2000
IDENTIFIER_PATTERN = re.compile(r"([0-9]+)(?:\.0+)?\Z")


class PaymentReferenceImportError(ValueError):
    pass


def normalize_name_key(value: object) -> str:
    raw = unicodedata.normalize("NFKD", str(value or "").upper())
    plain = "".join(character for character in raw if not unicodedata.combining(character))
    return " ".join(re.sub(r"[^A-Z0-9]+", " ", plain).split())


def normalize_pin_key(value: object) -> str | None:
    match = IDENTIFIER_PATTERN.fullmatch(str(value or "").strip())
    if match is None:
        return None
    normalized = match.group(1).lstrip("0")
    return normalized or None


def normalize_member_id(value: object) -> str | None:
    match = IDENTIFIER_PATTERN.fullmatch(str(value or "").strip())
    if match is None or not any(c != "0" for c in match.group(1)):
        return None
    return match.group(1)


@dataclass(frozen=True)
class PaymentReferenceValidation:
    source_sha256: str
    row_count: int
    active_at_cutoff: int
    expired_at_cutoff: int


def _hash_source(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def iter_reference_rows(path: Path):
    """CSV is UTF-8 with or without BOM; reject incomplete/ambiguous identity."""
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None or any(
            name not in reader.fieldnames for name in REQUIRED_HEADERS
        ):
            raise PaymentReferenceImportError(
                "El CSV debe incluir ID Socio, Nombre, PIN, Sucursal y Estado."
            )
        for number, row in enumerate(reader, 2):
            member_id = normalize_member_id(row["ID Socio"])
            name = (row["Nombre"] or "").strip()
            name_key = normalize_name_key(name)
            pin = (row["PIN"] or "").strip()
            pin_key = normalize_pin_key(pin)
            branch = (row["Sucursal"] or "").strip()
            status = (row["Estado"] or "").strip()
            if (
                not member_id or not name_key or not pin_key
                or not branch or status not in VALID_STATES
                or len(member_id) > 64 or len(name) > 255
                or len(name_key) > 255 or len(pin) > 64
                or len(branch) > 255
            ):
                raise PaymentReferenceImportError(
                    f"Identidad o estado inválido en fila {number}."
                )
            yield {
                "member_id": member_id,
                "name": name,
                "name_key": name_key,
                "pin": pin,
                "pin_key": pin_key,
                "branch": branch,
                "status_at_cutoff": status.upper(),
            }


def validate_payment_reference_csv(path: Path) -> PaymentReferenceValidation:
    path = Path(path)
    if not path.is_file():
        raise PaymentReferenceImportError("El archivo CSV no existe.")
    seen_members: set[str] = set()
    seen_keys: dict[tuple[str, str], str] = {}
    count = active = expired = 0
    for row in iter_reference_rows(path):
        member_id = row["member_id"]
        key = (row["name_key"], row["pin_key"])
        if member_id in seen_members:
            raise PaymentReferenceImportError(
                "ID Socio duplicado en el archivo de referencia."
            )
        previous = seen_keys.get(key)
        if previous is not None:
            raise PaymentReferenceImportError(
                "La combinación nombre + PIN no es única; importación rechazada."
            )
        seen_members.add(member_id)
        seen_keys[key] = member_id
        count += 1
        if row["status_at_cutoff"] == "ACTIVO":
            active += 1
        else:
            expired += 1
    if count == 0:
        raise PaymentReferenceImportError("El archivo no contiene socios.")
    return PaymentReferenceValidation(
        source_sha256=_hash_source(path),
        row_count=count,
        active_at_cutoff=active,
        expired_at_cutoff=expired,
    )


def _archive_source(path: Path, archive_dir: Path, sha256: str) -> Path:
    """Keep the raw source in a backend-only directory, not /uploads or Git."""
    archive_dir = Path(archive_dir)
    archive_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    destination = archive_dir / f"payment-reference-{sha256}.csv"
    if destination.exists():
        if _hash_source(destination) != sha256:
            raise PaymentReferenceImportError("El archivo archivado no coincide con el hash.")
        return destination
    # Exclusive and owner-only, so another import cannot silently replace it.
    try:
        fd = os.open(destination, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        if _hash_source(destination) != sha256:
            raise PaymentReferenceImportError("Archivo en conflicto en el archivo histórico.")
        return destination
    try:
        with os.fdopen(fd, "wb") as output, path.open("rb") as original:
            shutil.copyfileobj(original, output)
    except BaseException:
        destination.unlink(missing_ok=True)
        raise
    if _hash_source(destination) != sha256:
        destination.unlink(missing_ok=True)
        raise PaymentReferenceImportError("El archivo cambió durante el archivado.")
    return destination


def import_payment_reference_csv(
    *, file_path: Path, cutoff_date: date, archive_dir: Path,
    activate: bool = False, session=None,
) -> dict:
    """Import atomically after validation. Activation is an explicit opt-in."""
    if not isinstance(cutoff_date, date):
        raise PaymentReferenceImportError("Se requiere fecha de corte.")
    source = Path(file_path)
    validated = validate_payment_reference_csv(source)
    archive = _archive_source(source, Path(archive_dir), validated.source_sha256)
    active_session = session if session is not None else db.session

    try:
        existing = active_session.query(ContactCenterPaymentReferenceBatchORM).filter(
            ContactCenterPaymentReferenceBatchORM.source_sha256 == validated.source_sha256
        ).one_or_none()
        if existing is not None:
            if existing.cutoff_date != cutoff_date or existing.row_count != validated.row_count:
                raise PaymentReferenceImportError("El archivo existente tiene metadatos distintos.")
            batch = existing
            already_exists = True
        else:
            batch = ContactCenterPaymentReferenceBatchORM(
                cutoff_date=cutoff_date,
                source_filename=source.name[:255],
                source_sha256=validated.source_sha256,
                row_count=validated.row_count,
                is_active=False,
            )
            active_session.add(batch)
            active_session.flush()
            pending: list[dict] = []
            for row in iter_reference_rows(archive):
                pending.append({"batch_id": batch.id, **row})
                if len(pending) >= CHUNK_SIZE:
                    active_session.execute(insert(ContactCenterPaymentReferenceRowORM), pending)
                    pending.clear()
            if pending:
                active_session.execute(insert(ContactCenterPaymentReferenceRowORM), pending)
            already_exists = False
        if activate:
            active_session.execute(
                update(ContactCenterPaymentReferenceBatchORM)
                .where(ContactCenterPaymentReferenceBatchORM.is_active.is_(True))
                .values(is_active=False)
            )
            active_session.flush()
            batch.is_active = True
        active_session.commit()
    except BaseException:
        active_session.rollback()
        raise
    return {
        "batch_id": int(batch.id),
        "cutoff_date": cutoff_date.isoformat(),
        "source_sha256": validated.source_sha256,
        "row_count": validated.row_count,
        "active_at_cutoff": validated.active_at_cutoff,
        "expired_at_cutoff": validated.expired_at_cutoff,
        "already_exists": already_exists,
        "activated": bool(activate),
    }
