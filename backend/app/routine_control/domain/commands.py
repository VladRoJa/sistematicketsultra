from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any


@dataclass(frozen=True, slots=True)
class UpsertRoutineMemberCommand:
    source_system: str
    source_record_id: str
    source_identity_key: str
    external_member_id: str
    external_sale_id: str | None
    sucursal_id: int | None
    source_branch_name: str | None
    member_name: str | None
    email_original: str | None
    email_normalized: str | None
    sale_date: date
    source_updated_at_utc: datetime | None
    payload_hash: str
    source_metadata: dict[str, Any] | None
    observed_at_utc: datetime | None = None
