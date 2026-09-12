from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from app.demo_environment import service
from app.models.sucursal_model import SucursalOperationalStatus


class _Session:
    def __init__(self):
        self.added = []
        self.flush_count = 0

    def add(self, value):
        self.added.append(value)
        if getattr(value, "sucursal_id", None) is None:
            value.sucursal_id = 999

    def flush(self):
        self.flush_count += 1


def test_ensure_demo_branch_creates_active_demo_without_magic_id():
    session = _Session()

    with (
        patch.object(service, "_find_demo_branch", return_value=None),
        patch.object(service, "_assert_demo_isolation") as assert_isolation,
    ):
        result = service.ensure_demo_branch(session)

    assert result.created is True
    assert result.sucursal_id == 999
    assert result.sucursal == service.DEMO_BRANCH_NAME
    assert result.serie == service.DEMO_BRANCH_SERIE
    assert len(session.added) == 1

    branch = session.added[0]
    assert branch.is_demo is True
    assert branch.operational_status == SucursalOperationalStatus.ACTIVA
    assert branch.orden_apertura is None
    assert_isolation.assert_called_once_with(session, branch)


def test_ensure_demo_branch_is_idempotent_and_keeps_customized_identity():
    session = _Session()
    branch = SimpleNamespace(
        sucursal_id=321,
        sucursal="SHOWROOM ULTRA",
        serie="DEMO",
        is_demo=True,
        operational_status=SucursalOperationalStatus.PAUSADA,
        direccion="Dirección personalizada",
    )

    with (
        patch.object(service, "_find_demo_branch", return_value=branch),
        patch.object(service, "_assert_demo_isolation") as assert_isolation,
    ):
        result = service.ensure_demo_branch(session)

    assert result.created is False
    assert result.sucursal_id == 321
    assert result.sucursal == "SHOWROOM ULTRA"
    assert branch.operational_status == SucursalOperationalStatus.ACTIVA
    assert branch.direccion == "Dirección personalizada"
    assert session.added == []
    assert_isolation.assert_called_once_with(session, branch)


def test_ensure_demo_branch_refuses_to_convert_real_branch_silently():
    session = _Session()
    branch = SimpleNamespace(
        sucursal_id=55,
        sucursal="Sucursal real",
        serie="DEMO",
        is_demo=False,
        operational_status=SucursalOperationalStatus.ACTIVA,
    )

    with patch.object(service, "_find_demo_branch", return_value=branch):
        with pytest.raises(service.DemoEnvironmentError):
            service.ensure_demo_branch(session)

    assert session.added == []
