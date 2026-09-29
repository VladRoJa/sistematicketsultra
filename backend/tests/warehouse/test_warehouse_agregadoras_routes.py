from pathlib import Path

from flask import Flask

import app.routes.warehouse_agregadoras_routes as routes


def _unwrapped(endpoint):
    value = getattr(endpoint, "__wrapped__", None)
    assert value is not None
    return value


def test_status_requires_warehouse_view(monkeypatch):
    app = Flask(__name__)
    app.config["TESTING"] = True

    forbidden = ("forbidden", 403)
    monkeypatch.setattr(
        routes,
        "require_warehouse_view",
        lambda: forbidden,
    )

    called = {"service": False}

    def forbidden_service():
        called["service"] = True
        raise AssertionError("No debe consultar status sin permiso.")

    monkeypatch.setattr(
        routes,
        "get_agregadoras_consolidado_status",
        forbidden_service,
    )

    with app.test_request_context(
        "/api/warehouse/agregadoras-consolidado/status"
    ):
        result = _unwrapped(
            routes.agregadoras_consolidado_status
        )()

    assert result == forbidden
    assert called["service"] is False


def test_status_returns_service_payload_when_allowed(monkeypatch):
    app = Flask(__name__)
    app.config["TESTING"] = True

    monkeypatch.setattr(
        routes,
        "require_warehouse_view",
        lambda: None,
    )
    monkeypatch.setattr(
        routes,
        "get_agregadoras_consolidado_status",
        lambda: {
            "template_ready": True,
            "generated": True,
            "cutoff_date": "2026-09-29",
        },
    )

    with app.test_request_context(
        "/api/warehouse/agregadoras-consolidado/status"
    ):
        response, status_code = _unwrapped(
            routes.agregadoras_consolidado_status
        )()

    assert status_code == 200
    assert response.get_json() == {
        "template_ready": True,
        "generated": True,
        "cutoff_date": "2026-09-29",
    }


def test_download_requires_view_and_uses_generated_filename(
    monkeypatch,
):
    app = Flask(__name__)
    app.config["TESTING"] = True

    monkeypatch.setattr(
        routes,
        "require_warehouse_view",
        lambda: None,
    )
    monkeypatch.setattr(
        routes,
        "get_agregadoras_consolidado_download",
        lambda: (
            Path("/tmp/agregadoras.xlsx"),
            "Agregadoras 1 enero - 29 septiembre 2026.xlsx",
        ),
    )

    captured = {}

    def fake_send_file(path, **kwargs):
        captured["path"] = path
        captured.update(kwargs)
        return "sent"

    monkeypatch.setattr(routes, "send_file", fake_send_file)

    with app.test_request_context(
        "/api/warehouse/agregadoras-consolidado/download"
    ):
        result = _unwrapped(
            routes.agregadoras_consolidado_download
        )()

    assert result == "sent"
    assert captured["path"] == Path("/tmp/agregadoras.xlsx")
    assert captured["as_attachment"] is True
    assert (
        captured["download_name"]
        == "Agregadoras 1 enero - 29 septiembre 2026.xlsx"
    )
    assert captured["mimetype"].endswith(
        "spreadsheetml.sheet"
    )


def test_generate_requires_upload_and_maps_controlled_error_to_409(
    monkeypatch,
):
    app = Flask(__name__)
    app.config["TESTING"] = True

    monkeypatch.setattr(
        routes,
        "require_warehouse_upload",
        lambda: None,
    )

    def fail_generation():
        raise routes.AgregadorasConsolidadoError(
            "Falta continuidad diaria."
        )

    monkeypatch.setattr(
        routes,
        "generate_agregadoras_consolidado",
        fail_generation,
    )

    with app.test_request_context(
        "/api/warehouse/agregadoras-consolidado/generate",
        method="POST",
    ):
        response, status_code = _unwrapped(
            routes.agregadoras_consolidado_generate
        )()

    assert status_code == 409
    payload = response.get_json()
    assert payload["error"] == (
        "No se pudo generar el consolidado"
    )
    assert payload["detail"] == "Falta continuidad diaria."
