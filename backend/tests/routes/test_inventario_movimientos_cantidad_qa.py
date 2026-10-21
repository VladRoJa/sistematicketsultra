"""QA-02: las cantidades inválidas no crean movimientos ni tocan stock."""

from unittest.mock import Mock

import pytest
from flask import Flask
from flask_jwt_extended import JWTManager, create_access_token

from app.routes import inventarios as inventory_routes


@pytest.fixture
def qa_client(monkeypatch):
    app = Flask(__name__)
    app.config.update(TESTING=True, JWT_SECRET_KEY="inventory-qa02-synthetic-only")
    JWTManager(app)
    app.register_blueprint(inventory_routes.inventario_bp)

    monkeypatch.setattr(
        inventory_routes, "_get_current_user_id_required", lambda: (91, None)
    )
    monkeypatch.setattr(
        inventory_routes, "_require_inventory_movement_write", lambda _sucursal: None
    )
    create_movement = Mock(
        side_effect=AssertionError("Una cantidad inválida no debe crear movimientos")
    )
    monkeypatch.setattr(inventory_routes, "MovimientoInventario", create_movement)

    with app.app_context():
        token = create_access_token(identity="91")

    return app.test_client(), token, create_movement


@pytest.mark.parametrize(
    "cantidad,expected",
    [
        (1, 1),
        (5, 5),
        ("3", 3),
        (" 7 ", 7),
        (0, None),
        (-4, None),
        (1.5, None),
        ("2.5", None),
        (True, None),
        (None, None),
    ],
)
def test_parse_positive_movement_quantity(cantidad, expected):
    assert inventory_routes._parse_positive_movement_quantity(cantidad) == expected


@pytest.mark.parametrize(
    "productos",
    [
        [{"inventario_id": 1, "cantidad": 0}],
        [{"inventario_id": 1, "cantidad": -5}],
        [{"inventario_id": 1, "cantidad": 1.5}],
        [{"inventario_id": 1, "cantidad": "2.5"}],
        [{"inventario_id": 1, "cantidad": True}],
        [{"inventario_id": 1}],
        [{"inventario_id": 1, "cantidad": 1}, {"inventario_id": 2, "cantidad": -1}],
        [None],
    ],
)
def test_invalid_quantity_rejected_before_writes(qa_client, productos):
    client, token, create_movement = qa_client
    response = client.post(
        "/api/inventario/movimientos",
        json={
            "tipo_movimiento": "salida",
            "sucursal_id": 1,
            "inventarios": productos,
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 400
    create_movement.assert_not_called()
