"""Contrato unitario de capacidades opt-in para coordinación Mantenimiento V1.

No requiere DB productiva ni privilegios globales.
"""

from types import SimpleNamespace
from unittest.mock import patch

from app.utils import tickets_maintenance_permissions as policy
from app.utils.pm_permissions import can_pm_execute, can_pm_validate


def actor(role="COMPRAS", user_id=91):
    return SimpleNamespace(id=user_id, rol=role)


def test_compras_sin_grant_sigue_solo_lectura():
    with (
        patch.object(policy, "can_pm_view", return_value=True),
        patch.object(policy, "_has_active_user_grant", return_value=False),
    ):
        assert policy.has_maintenance_coordination_permission(actor()) is False

    assert can_pm_execute(actor()) is False
    assert can_pm_validate(actor()) is False


def test_grant_de_coordinacion_necesita_visibilidad_pm():
    with (
        patch.object(policy, "can_pm_view", return_value=False),
        patch.object(policy, "_has_active_user_grant", return_value=True),
    ):
        assert policy.has_maintenance_coordination_permission(actor()) is False


def test_grant_individual_habilita_coordinacion_sin_escalar_ejecucion():
    with (
        patch.object(policy, "can_pm_view", return_value=True),
        patch.object(policy, "_has_active_user_grant", return_value=True) as check,
    ):
        assert policy.has_maintenance_coordination_permission(actor()) is True
        check.assert_called_once_with(actor(), policy.COORDINATE_ACTION)


def test_admin_puede_coordinar_sin_grant_individual():
    with patch.object(policy, "_has_active_user_grant") as check:
        assert policy.has_maintenance_coordination_permission(
            actor(role="ADMINISTRADOR")
        ) is True
        check.assert_not_called()


def test_visibilidad_assigned_only_se_activa_solo_con_grant_individual():
    with patch.object(policy, "_has_active_user_grant", return_value=False):
        assert policy.has_assigned_only_maintenance_scope(
            actor(role="SR_MANTENIMIENTO", user_id=68)
        ) is False

    with patch.object(policy, "_has_active_user_grant", return_value=True) as check:
        assert policy.has_assigned_only_maintenance_scope(
            actor(role="SR_MANTENIMIENTO", user_id=68)
        ) is True
        check.assert_called_once_with(
            actor(role="SR_MANTENIMIENTO", user_id=68),
            policy.ASSIGNED_ONLY_ACTION,
        )


def test_assigned_only_no_restringe_administradores():
    with patch.object(policy, "_has_active_user_grant") as check:
        assert policy.has_assigned_only_maintenance_scope(
            actor(role="ADMINISTRADOR")
        ) is False
        check.assert_not_called()
