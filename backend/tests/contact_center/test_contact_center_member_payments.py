from types import SimpleNamespace

import pytest
from flask import Flask

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
    assert payments._search_term("12345") == ("12345", True)
    assert payments._search_term("María") == ("María", False)


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


class _Session:
    def __init__(self, active, historical):
        self.active = active
        self.historical = historical

    def query(self, model):
        if model is payments.SociosActivosSnapshotRowORM:
            return _Query(self.active)
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
