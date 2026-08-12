from datetime import (
    datetime,
    timezone,
)

import pytest

from app.models import (
    MarketingIventasContactORM,
    MarketingIventasContactTagORM,
)
from app.services.marketing_iventas_service import (
    normalize_iventas_contact,
)
from app.services.marketing_iventas_structured_persistence_service import (
    MarketingIventasStructuredPersistenceError,
    persist_iventas_normalized_page,
)


class FakeQuery:
    def __init__(
        self,
        session,
        model,
    ):
        self.session = session
        self.model = model
        self.filters = {}

    def filter_by(
        self,
        **kwargs,
    ):
        self.filters = kwargs
        return self

    def first(self):
        if self.model is MarketingIventasContactORM:
            key = (
                self.filters["sync_run_id"],
                self.filters["branch_code"],
                self.filters["contact_id"],
            )

            return (
                self.session
                .existing_contacts
                .get(key)
            )

        raise AssertionError(
            "first() inesperado."
        )

    def all(self):
        if self.model is MarketingIventasContactTagORM:
            contact_row_id = self.filters[
                "iventas_contact_row_id"
            ]

            return list(
                self.session
                .existing_tags
                .get(
                    contact_row_id,
                    [],
                )
            )

        raise AssertionError(
            "all() inesperado."
        )


class FakeSession:
    def __init__(self):
        self.existing_contacts = {}
        self.existing_tags = {}

        self.added = []
        self.added_many = []

        self.flush_count = 0
        self.commit_count = 0
        self.rollback_count = 0

        self.next_contact_id = 100

    def query(
        self,
        model,
    ):
        return FakeQuery(
            self,
            model,
        )

    def add(
        self,
        obj,
    ):
        self.added.append(obj)

    def add_all(
        self,
        rows,
    ):
        self.added_many.extend(
            rows
        )

    def flush(self):
        self.flush_count += 1

        for item in self.added:
            if (
                isinstance(
                    item,
                    MarketingIventasContactORM,
                )
                and item.id is None
            ):
                item.id = (
                    self.next_contact_id
                )

                self.next_contact_id += 1

    def commit(self):
        self.commit_count += 1

    def rollback(self):
        self.rollback_count += 1


def _raw_contact(
    *,
    contact_id="contact-001",
    tags=None,
):
    return {
        "id": contact_id,
        "name": "Contacto prueba",
        "phone": "+52 686 123 4567",
        "createdAt": (
            "2026-08-01T18:30:45Z"
        ),
        "firstMessageAt": (
            "2026-08-01T18:35:00Z"
        ),
        "lastOutboundMessageAt": (
            "2026-08-01T19:00:00Z"
        ),
        "lastMessageStatus": "delivered",
        "channel": {
            "id": "channel-01",
            "name": "Canal",
            "phone": "526861111111",
            "platform": "whatsapp",
        },
        "agent": {
            "id": "agent-01",
            "name": "Agente",
        },
        "tags": (
            [
                "ad_fb_123456789",
                "seguimiento",
            ]
            if tags is None
            else tags
        ),
    }


def _normalized(
    *,
    contact_id="contact-001",
    branch_code="papalote",
    sucursal_id=13,
    tags=None,
):
    return normalize_iventas_contact(
        contact=_raw_contact(
            contact_id=contact_id,
            tags=tags,
        ),
        branch_code=branch_code,
        sucursal_id=sucursal_id,
    )


def _observed_at():
    return datetime(
        2026,
        8,
        9,
        3,
        10,
        tzinfo=timezone.utc,
    )


def test_new_contact_and_tags_commit_as_one_page(
) -> None:
    session = FakeSession()

    normalized = _normalized()

    result = persist_iventas_normalized_page(
        sync_run_id=7,
        contacts=[normalized],
        observed_at=_observed_at(),
        session=session,
    )

    assert result.contacts_received == 1
    assert result.contacts_created == 1
    assert result.contacts_existing == 0
    assert result.tags_created == 2

    assert result.contact_row_ids == (
        100,
    )

    assert session.flush_count == 1
    assert session.commit_count == 1
    assert session.rollback_count == 0

    assert len(session.added) == 1

    contact_row = session.added[0]

    assert isinstance(
        contact_row,
        MarketingIventasContactORM,
    )

    assert contact_row.id == 100
    assert contact_row.sync_run_id == 7
    assert contact_row.sucursal_id == 13
    assert contact_row.branch_code == "papalote"
    assert contact_row.contact_id == "contact-001"
    assert contact_row.row_hash == normalized.row_hash

    assert len(session.added_many) == 2

    for tag_row in session.added_many:
        assert isinstance(
            tag_row,
            MarketingIventasContactTagORM,
        )

        assert tag_row.sync_run_id == 7
        assert tag_row.iventas_contact_row_id == 100
        assert tag_row.branch_code == "papalote"
        assert tag_row.contact_id == "contact-001"
        assert (
            tag_row.observed_at
            == _observed_at()
        )


def test_contact_without_tags_is_valid(
) -> None:
    session = FakeSession()

    result = persist_iventas_normalized_page(
        sync_run_id=7,
        contacts=[
            _normalized(
                tags=[],
            )
        ],
        observed_at=_observed_at(),
        session=session,
    )

    assert result.contacts_created == 1
    assert result.tags_created == 0
    assert session.added_many == []
    assert session.commit_count == 1


def test_existing_exact_snapshot_is_idempotent(
) -> None:
    session = FakeSession()

    normalized = _normalized()

    existing = MarketingIventasContactORM(
        id=41,
        sync_run_id=7,
        sucursal_id=13,
        branch_code="papalote",
        contact_id="contact-001",
        created_at_utc=(
            normalized.created_at_utc
        ),
        created_at_local=(
            normalized.created_at_local
        ),
        created_date_local=(
            normalized.created_date_local
        ),
        phone_match_status=(
            normalized.phone_match_status
        ),
        row_hash=normalized.row_hash,
    )

    session.existing_contacts[
        (
            7,
            "papalote",
            "contact-001",
        )
    ] = existing

    session.existing_tags[41] = [
        MarketingIventasContactTagORM(
            sync_run_id=7,
            iventas_contact_row_id=41,
            branch_code="papalote",
            contact_id="contact-001",
            tag_raw=tag.tag_raw,
            tag_kind=tag.tag_kind,
            meta_ad_id=tag.meta_ad_id,
            observed_at=_observed_at(),
        )
        for tag in normalized.tags
    ]

    result = persist_iventas_normalized_page(
        sync_run_id=7,
        contacts=[normalized],
        observed_at=_observed_at(),
        session=session,
    )

    assert result.contacts_received == 1
    assert result.contacts_created == 0
    assert result.contacts_existing == 1
    assert result.tags_created == 0
    assert result.contact_row_ids == (
        41,
    )

    assert session.added == []
    assert session.added_many == []
    assert session.commit_count == 0
    assert session.rollback_count == 0


def test_existing_contact_with_different_row_hash_fails(
) -> None:
    session = FakeSession()

    normalized = _normalized()

    existing = MarketingIventasContactORM(
        id=41,
        sync_run_id=7,
        sucursal_id=13,
        branch_code="papalote",
        contact_id="contact-001",
        created_at_utc=(
            normalized.created_at_utc
        ),
        created_at_local=(
            normalized.created_at_local
        ),
        created_date_local=(
            normalized.created_date_local
        ),
        phone_match_status=(
            normalized.phone_match_status
        ),
        row_hash="0" * 64,
    )

    session.existing_contacts[
        (
            7,
            "papalote",
            "contact-001",
        )
    ] = existing

    with pytest.raises(
        MarketingIventasStructuredPersistenceError,
        match="contenido estructurado diferente",
    ):
        persist_iventas_normalized_page(
            sync_run_id=7,
            contacts=[normalized],
            observed_at=_observed_at(),
            session=session,
        )

    assert session.commit_count == 0
    assert session.rollback_count == 1


def test_existing_contact_with_different_tags_fails(
) -> None:
    session = FakeSession()

    normalized = _normalized()

    existing = MarketingIventasContactORM(
        id=41,
        sync_run_id=7,
        sucursal_id=13,
        branch_code="papalote",
        contact_id="contact-001",
        created_at_utc=(
            normalized.created_at_utc
        ),
        created_at_local=(
            normalized.created_at_local
        ),
        created_date_local=(
            normalized.created_date_local
        ),
        phone_match_status=(
            normalized.phone_match_status
        ),
        row_hash=normalized.row_hash,
    )

    session.existing_contacts[
        (
            7,
            "papalote",
            "contact-001",
        )
    ] = existing

    session.existing_tags[41] = []

    with pytest.raises(
        MarketingIventasStructuredPersistenceError,
        match="tags diferentes",
    ):
        persist_iventas_normalized_page(
            sync_run_id=7,
            contacts=[normalized],
            observed_at=_observed_at(),
            session=session,
        )

    assert session.commit_count == 0
    assert session.rollback_count == 1


def test_duplicate_contact_inside_page_fails(
) -> None:
    session = FakeSession()

    normalized = _normalized()

    with pytest.raises(
        MarketingIventasStructuredPersistenceError,
        match="duplicado",
    ):
        persist_iventas_normalized_page(
            sync_run_id=7,
            contacts=[
                normalized,
                normalized,
            ],
            observed_at=_observed_at(),
            session=session,
        )

    assert session.added == []
    assert session.commit_count == 0


def test_page_cannot_mix_branches(
) -> None:
    session = FakeSession()

    with pytest.raises(
        ValueError,
        match="mezclar branch_code",
    ):
        persist_iventas_normalized_page(
            sync_run_id=7,
            contacts=[
                _normalized(
                    contact_id="contact-001",
                    branch_code="papalote",
                    sucursal_id=13,
                ),
                _normalized(
                    contact_id="contact-002",
                    branch_code="carrousel",
                    sucursal_id=12,
                ),
            ],
            observed_at=_observed_at(),
            session=session,
        )


def test_observed_at_requires_timezone(
) -> None:
    with pytest.raises(
        ValueError,
        match="timezone",
    ):
        persist_iventas_normalized_page(
            sync_run_id=7,
            contacts=[],
            observed_at=datetime(
                2026,
                8,
                9,
                3,
                10,
            ),
            session=FakeSession(),
        )


def test_sync_run_id_must_be_positive(
) -> None:
    with pytest.raises(
        ValueError,
        match="sync_run_id",
    ):
        persist_iventas_normalized_page(
            sync_run_id=0,
            contacts=[],
            observed_at=_observed_at(),
            session=FakeSession(),
        )
