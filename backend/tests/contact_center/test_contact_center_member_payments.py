from types import SimpleNamespace
from datetime import date

import pytest
from flask import Flask
from sqlalchemy.dialects import postgresql

from app.routes import contact_center_routes as routes
from app.services import contact_center_member_payment_service as payments
from app.services.contact_center_service import ContactCenterValidationError
from app.utils.contact_center_access import ContactCenterAuthorizationError


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("12345", "12345"),
        ("001234", "001234"),
        ("12345.0", "12345"),
        ("12345.00", "12345"),
        ("0", None),
        ("", None),
        ("1&admin=true", None),
        ("abc123", None),
        ("2.3", None),
    ],
)
def test_payment_member_id_is_safe_and_keeps_leading_zeroes(raw, expected):
    assert payments._valid_member_id(raw) == expected


def test_payment_url_uses_only_valid_socios_id():
    row = payments._member_payload(
        member_id="00123.0",
        name="María",
        pin="45678",
        branch="VILLAS_DEL_REY",
        source="ACTIVO",
    )
    assert row["member_id"] == "00123"
    assert row["payment_url"] == "https://pago.ultragym.com.mx?sid=00123"
    assert payments._member_payload(
        member_id="not-an-id", name="x", pin="1", branch="x", source="ACTIVO"
    ) is None


@pytest.mark.parametrize("raw", ["", "A", "ab", "a" * 81])
def test_lookup_rejects_short_or_excessive_queries(raw):
    with pytest.raises(ContactCenterValidationError):
        payments._search_term(raw)


def test_lookup_escapes_like_wildcards():
    assert payments._escaped_like(r"ana%_") == r"%ana\%\_%"
    assert payments._search_term("12345") == ("12345", "PIN")
    assert payments._search_term("María") == ("María", "NAME")


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("6861234567", ("6861234567", "PHONE")),
        ("+52 (686) 123-4567", ("6861234567", "PHONE")),
        ("5216861234567", ("6861234567", "PHONE")),
        ("686 123 4567", ("6861234567", "PHONE")),
        ("12345", ("12345", "PIN")),
        ("Ana Pérez", ("Ana Pérez", "NAME")),
    ],
)
def test_search_term_detects_complete_mx_phones_without_confusing_pins(raw, expected):
    assert payments._search_term(raw) == expected


@pytest.mark.parametrize(
    ("phone_column", "lada_column", "already_digits"),
    [
        (payments.SociosActivosSnapshotRowORM.telefono_digits,
         payments.SociosActivosSnapshotRowORM.lada_raw, True),
        (payments.VentasNuevosSociosDetalleSnapshotRowORM.telefono,
         payments.VentasNuevosSociosDetalleSnapshotRowORM.lada, False),
    ],
)
def test_phone_filter_supports_direct_and_lada_local_numbers(
    phone_column, lada_column, already_digits
):
    expression = payments._phone_filter(
        phone_column, lada_column, "6861234567", digits_stored=already_digits
    )
    sql = str(expression.compile(
        dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
    ))
    assert "6861234567" in sql
    assert "526861234567" in sql
    assert "5216861234567" in sql
    assert "concat(" in sql
    if not already_digits:
        assert "regexp_replace(" in sql


def test_phone_search_requires_full_valid_number():
    assert payments._search_term("68612345") == ("68612345", "PIN")
    assert payments._search_term("+52 686 123") == ("+52 686 123", "NAME")



class _Query:
    def __init__(self, rows):
        self.rows = rows

    def filter(self, *_args):
        return self

    def join(self, *_args):
        return self

    def order_by(self, *_args):
        return self

    def limit(self, *_args):
        return self

    def all(self):
        return self.rows

    def one_or_none(self):
        return self.rows[0] if self.rows else None


class _Session:
    def __init__(self, active, historical, *, expired=None, reference=None, batch=None):
        self.active = active
        self.historical = historical
        self.expired = expired or []
        self.reference = reference or []
        self.batch = batch

    def query(self, model):
        if model is payments.SociosActivosSnapshotRowORM:
            return _Query(self.active)
        if model is payments.SociosVencidosCarteraORM:
            return _Query(self.expired)
        if model is payments.ContactCenterPaymentReferenceBatchORM:
            return _Query([self.batch] if self.batch else [])
        if model is payments.ContactCenterPaymentReferenceRowORM:
            return _Query(self.reference)
        return _Query(self.historical)


def test_search_prefers_canonical_actives_and_deduplicates_history(monkeypatch):
    monkeypatch.setattr(
        payments,
        "resolve_latest_canonical_socios_activos_snapshot",
        lambda **_kwargs: SimpleNamespace(id=9),
    )
    active = [
        SimpleNamespace(
            id=1, id_socio="111", nombre="Ana Pérez", pin="1234",
            sucursal_raw="VILLAS_DEL_REY",
        )
    ]
    historical = [
        SimpleNamespace(
            id=3, id_socio="111", nombre="Ana", apellido_paterno="Pérez",
            apellido_materno="", pin="1234", sucursal_raw="VILLA_VERDE",
        ),
        SimpleNamespace(
            id=2, id_socio="222", nombre="Ana", apellido_paterno="Ruiz",
            apellido_materno="López", pin="9876", sucursal_raw="VILLA_VERDE",
        ),
    ]
    rows = payments.search_contact_center_member_payments(
        "Ana", session=_Session(active, historical)
    )
    assert [row["member_id"] for row in rows] == ["111", "222"]
    assert rows[0]["branch"] == "VILLAS_DEL_REY"
    assert rows[0]["source"] == "ACTIVO"
    assert rows[1]["name"] == "Ana Ruiz López"
    assert rows[1]["payment_url"].endswith("sid=222")


def test_phone_search_deduplicates_and_matches_only_exact_normalized_phone(monkeypatch):
    monkeypatch.setattr(
        payments,
        "resolve_latest_canonical_socios_activos_snapshot",
        lambda **_kwargs: SimpleNamespace(id=9),
    )
    active = [
        SimpleNamespace(
            id=1, id_socio="111", nombre="Ana Pérez", pin="3456",
            sucursal_raw="VILLAS_DEL_REY", lada_raw="686",
            telefono_raw="1234567",
        ),
        SimpleNamespace(
            id=2, id_socio="333", nombre="Otra persona", pin="9999",
            sucursal_raw="SEND_MXL", lada_raw="686",
            telefono_raw="1234568",
        ),
    ]
    historical = [
        SimpleNamespace(
            id=4, id_socio="111", nombre="Ana", apellido_paterno="Pérez",
            apellido_materno="", pin="3456", sucursal_raw="VILLA_VERDE",
            lada="52", telefono="6861234567",
        ),
        SimpleNamespace(
            id=3, id_socio="222", nombre="Luis", apellido_paterno="López",
            apellido_materno="", pin="3211", sucursal_raw="VILLA_VERDE",
            lada="", telefono="+52 (686) 123-4567",
        ),
    ]
    rows = payments.search_contact_center_member_payments(
        "+52 686 123 4567", session=_Session(active, historical)
    )
    assert [row["member_id"] for row in rows] == ["111", "222"]
    assert rows[0]["source"] == "ACTIVO"
    assert rows[1]["source"] == "HISTORICO_ALTAS"
    assert all(
        row["payment_url"].endswith(f"sid={row['member_id']}")
        for row in rows
    )


def test_phone_search_does_not_guess_ids_for_unsupported_number(monkeypatch):
    monkeypatch.setattr(
        payments,
        "resolve_latest_canonical_socios_activos_snapshot",
        lambda **_kwargs: SimpleNamespace(id=9),
    )
    rows = payments.search_contact_center_member_payments(
        "6861234567",
        session=_Session(
            active=[
                SimpleNamespace(
                    id=1, id_socio="999", nombre="Alguien", pin="33",
                    sucursal_raw="VILLA_VERDE", lada_raw="686",
                    telefono_raw="7654321",
                )
            ],
            historical=[],
        ),
    )
    assert rows == []



def test_expired_member_resolves_id_from_name_and_pin_not_branch(monkeypatch):
    monkeypatch.setattr(
        payments, "resolve_latest_canonical_socios_activos_snapshot",
        lambda **_kwargs: None,
    )
    expired = [SimpleNamespace(
        id=1, nombre="José María Gómez", pin="000987", sucursal_raw="VILLA_VERDE",
        fecha_vencimiento_date=date(2026, 10, 30), telefono_raw="6861234567",
    )]
    batch = SimpleNamespace(id=11, cutoff_date=date(2026, 10, 31))
    reference = [SimpleNamespace(
        name_key="JOSE MARIA GOMEZ", pin_key="987", member_id="13579"
    )]
    rows = payments.search_contact_center_member_payments(
        "+52 686 123 4567",
        session=_Session([], [], expired=expired, reference=reference, batch=batch),
    )
    assert len(rows) == 1
    assert rows[0]["member_id"] == "13579"
    assert rows[0]["payment_url"] == "https://pago.ultragym.com.mx?sid=13579"
    assert rows[0]["source"] == "VENCIDO_REFERENCIA"
    assert rows[0]["branch"] == "VILLA_VERDE"
    assert rows[0]["reference_cutoff_date"] == "2026-10-31"


def test_expired_member_without_exact_name_pin_never_gets_link(monkeypatch):
    monkeypatch.setattr(
        payments, "resolve_latest_canonical_socios_activos_snapshot",
        lambda **_kwargs: None,
    )
    expired = [SimpleNamespace(
        id=1, nombre="María López", pin="54321", sucursal_raw="VILLAS_DEL_REY",
        fecha_vencimiento_date=date(2026, 10, 25), telefono_raw="6861234567",
    )]
    reference = [SimpleNamespace(
        name_key="MARIA PEREZ", pin_key="54321", member_id="123"
    )]
    rows = payments.search_contact_center_member_payments(
        "54321",
        session=_Session(
            [], [], expired=expired, reference=reference,
            batch=SimpleNamespace(id=11, cutoff_date=date(2026, 10, 31)),
        ),
    )
    assert len(rows) == 1
    assert rows[0]["source"] == "VENCIDO_SIN_ID"
    assert rows[0]["member_id"] is None
    assert rows[0]["payment_url"] is None


def test_expired_lookup_without_import_returns_unverified_not_bogus_link(monkeypatch):
    monkeypatch.setattr(
        payments, "resolve_latest_canonical_socios_activos_snapshot",
        lambda **_kwargs: None,
    )
    expired = [SimpleNamespace(
        id=1, nombre="ANA GARCIA", pin="789", sucursal_raw="PASEO 2000",
        fecha_vencimiento_date=date(2026, 10, 25), telefono_raw="6861234567",
    )]
    rows = payments.search_contact_center_member_payments(
        "ANA",
        session=_Session([], [], expired=expired),
    )
    assert rows[0]["member_id"] is None
    assert rows[0]["payment_url"] is None


def test_expired_history_deduplicates_repeated_episodes(monkeypatch):
    monkeypatch.setattr(
        payments, "resolve_latest_canonical_socios_activos_snapshot",
        lambda **_kwargs: None,
    )
    expired = [
        SimpleNamespace(
            id=2, nombre="PEDRO LOPEZ", pin="111", sucursal_raw="PASEO 2000",
            fecha_vencimiento_date=date(2026, 10, 30), telefono_raw=None,
        ),
        SimpleNamespace(
            id=1, nombre="Pedro López", pin="111", sucursal_raw="SEND MXL",
            fecha_vencimiento_date=date(2026, 8, 12), telefono_raw=None,
        ),
    ]
    rows = payments.search_contact_center_member_payments(
        "Pedro", session=_Session([], [], expired=expired)
    )
    assert len(rows) == 1
    assert rows[0]["branch"] == "PASEO 2000"




def test_manager_is_denied_before_member_query(monkeypatch):
    monkeypatch.setattr(
        routes, "_context",
        lambda: (object(), SimpleNamespace(is_manager=True)),
    )

    def must_not_query(_query):
        pytest.fail("Manager must not reach payment lookup")

    monkeypatch.setattr(
        routes, "search_contact_center_member_payments", must_not_query
    )
    with Flask(__name__).test_request_context("/member-payments?q=Ana"):
        with pytest.raises(ContactCenterAuthorizationError):
            routes.search_member_payments.__wrapped__()


def test_operator_search_returns_only_expected_fields(monkeypatch):
    monkeypatch.setattr(
        routes, "_context",
        lambda: (object(), SimpleNamespace(is_manager=False)),
    )
    monkeypatch.setattr(
        routes, "search_contact_center_member_payments",
        lambda query: [
            {
                "member_id": "12", "name": "Ana", "pin": "45",
                "branch": "VILLAS_DEL_REY", "source": "ACTIVO",
                "payment_url": "https://pago.ultragym.com.mx?sid=12",
            }
        ] if query == "Ana" else [],
    )
    with Flask(__name__).test_request_context("/member-payments?q=Ana"):
        response, status = routes.search_member_payments.__wrapped__()
        assert status == 200
        assert response.json["count"] == 1
        assert response.json["rows"][0]["member_id"] == "12"
