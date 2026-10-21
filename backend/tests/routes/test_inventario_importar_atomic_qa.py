"""QA-07: importaciones sintéticas, sin PostgreSQL ni archivos persistidos."""

from io import BytesIO
from types import SimpleNamespace
from unittest.mock import Mock

import pandas as pd
import pytest
from flask import Flask
from flask_jwt_extended import JWTManager, create_access_token

from app.routes import inventarios as routes


class ProductoSintetico:
    nombre = object()
    marca = object()

    def __init__(self, **campos):
        self.campos = campos


@pytest.fixture
def importar(monkeypatch):
    app = Flask(__name__)
    app.config.update(TESTING=True, JWT_SECRET_KEY="qa07-synthetic")
    JWTManager(app)
    app.register_blueprint(routes.inventario_bp)

    monkeypatch.setattr(routes, "_require_inventory_global_write", lambda: None)
    monkeypatch.setattr(routes, "InventarioGeneral", ProductoSintetico)
    session = Mock()
    session.query.return_value.all.return_value = []
    monkeypatch.setattr(routes, "db", SimpleNamespace(session=session))
    monkeypatch.setattr(
        routes, "manejar_error", lambda _error, _contexto: ({"error": "sintético"}, 500)
    )

    with app.app_context():
        token = create_access_token(identity="91")
    client = app.test_client()

    def enviar(contenido, filename="importacion.csv"):
        return client.post(
            "/api/inventario/importar",
            data={"file": (BytesIO(contenido), filename)},
            headers={"Authorization": f"Bearer {token}"},
            content_type="multipart/form-data",
        )

    return enviar, session


def test_csv_valido_importa_dos_filas_con_un_solo_commit(importar):
    enviar, session = importar
    contenido = (
        "nombre,tipo,categoria,marca,descripcion\n"
        "Banca QA,aparato,Equipo,FLEX,Primera\n"
        "Tapete QA,producto,Consumible,ULTRA,Segunda\n"
    ).encode()
    response = enviar(contenido)
    assert response.status_code == 200
    assert response.get_json()["agregados"] == 2
    session.add_all.assert_called_once()
    productos = session.add_all.call_args.args[0]
    assert [p.campos["nombre"] for p in productos] == ["Banca QA", "Tapete QA"]
    assert productos[0].campos["marca"] == "FLEX"
    session.commit.assert_called_once()
    session.rollback.assert_not_called()


def test_xlsx_valido_importa_una_fila(importar):
    enviar, session = importar
    output = BytesIO()
    pd.DataFrame([{"nombre": "Polea QA", "tipo": "aparato", "categoria": "Equipo"}]).to_excel(
        output, index=False
    )
    response = enviar(output.getvalue(), filename="plantilla.xlsx")
    assert response.status_code == 200
    session.add_all.assert_called_once()
    assert session.add_all.call_args.args[0][0].campos["marca"] == ""
    session.commit.assert_called_once()


@pytest.mark.parametrize(
    "contenido,filename",
    [
        (b"nombre,tipo,categoria\nValido,aparato,Equipo\n,aparato,Equipo\n", "lote.csv"),
        (b"nombre,tipo\nValido,aparato\n", "sin-categoria.csv"),
        (b"nombre,tipo,categoria,marca\nA,producto,Equipo,X\nA,producto,Equipo,X\n", "duplicado.csv"),
        (b"nombre,tipo,categoria\nValido,producto,Equipo\nB,producto,\n", "incompleto.csv"),
        (b"nombre,tipo,categoria\n", "vacio.csv"),
        (b"contenido-que-no-es-xlsx", "falso.xlsx"),
        (b"nombre,tipo,categoria\nValido,producto,Equipo\n", "prohibido.txt"),
    ],
)
def test_archivo_invalido_nunca_escribe(importar, contenido, filename):
    enviar, session = importar
    response = enviar(contenido, filename)
    assert response.status_code == 400
    session.add_all.assert_not_called()
    session.commit.assert_not_called()


def test_duplicado_con_catalogo_existente_rechaza_lote(importar):
    enviar, session = importar
    session.query.return_value.all.return_value = [("Banca QA", "FLEX")]
    csv = b"nombre,tipo,categoria,marca\nBanca QA,aparato,Equipo,FLEX\nOtro,producto,Equipo,O\n"
    response = enviar(csv)
    assert response.status_code == 409
    session.add_all.assert_not_called()
    session.commit.assert_not_called()
    session.rollback.assert_called_once()


def test_archivo_excesivo_rechazado_sin_escrituras(importar):
    enviar, session = importar
    response = enviar(b"x" * (10 * 1024 * 1024 + 1))
    assert response.status_code == 413
    session.add_all.assert_not_called()
    session.commit.assert_not_called()


def test_error_en_commit_hace_rollback(importar):
    enviar, session = importar
    session.commit.side_effect = RuntimeError("db-failure-synthetic")
    response = enviar(b"nombre,tipo,categoria\nValido,producto,Equipo\n")
    assert response.status_code == 500
    session.add_all.assert_called_once()
    session.commit.assert_called_once()
    session.rollback.assert_called_once()
