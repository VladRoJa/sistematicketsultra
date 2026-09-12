from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import func, or_

from app.models.sucursal_model import Sucursal, SucursalOperationalStatus
from app.models.suite_governance import SuiteSucursalRegionAssignmentORM
from app.models.warehouse import TrackBranchCatalogORM


DEMO_BRANCH_SERIE = "DEMO"
DEMO_BRANCH_NAME = "ULTRA DEMO"
DEMO_BRANCH_STATE = "DEMO"
DEMO_BRANCH_CITY = "DEMO"
DEMO_BRANCH_ADDRESS = "Entorno de demostración Suite Ultra"


class DemoEnvironmentError(RuntimeError):
    pass


@dataclass(frozen=True)
class DemoBranchProvisionResult:
    sucursal_id: int
    sucursal: str
    serie: str
    created: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "sucursal_id": self.sucursal_id,
            "sucursal": self.sucursal,
            "serie": self.serie,
            "created": self.created,
            "is_demo": True,
        }


def _find_demo_branch(session) -> Sucursal | None:
    """Resuelve la demo por semántica canónica o por su llave natural inicial."""

    rows = (
        session.query(Sucursal)
        .filter(
            or_(
                Sucursal.is_demo.is_(True),
                func.upper(func.trim(Sucursal.serie)) == DEMO_BRANCH_SERIE,
            )
        )
        .all()
    )

    if len(rows) > 1:
        raise DemoEnvironmentError(
            "Existe más de una candidata a sucursal DEMO; no es seguro provisionar."
        )

    return rows[0] if rows else None


def _assert_demo_isolation(session, branch: Sucursal) -> None:
    """Impide que la demo quede conectada accidentalmente al universo analítico."""

    track_link = (
        session.query(TrackBranchCatalogORM.sucursal_canon)
        .filter(TrackBranchCatalogORM.sucursal_id == branch.sucursal_id)
        .first()
    )
    if track_link is not None:
        raise DemoEnvironmentError(
            "ULTRA DEMO está vinculada a track_branch_catalog. "
            "Una sucursal demo no debe participar en Track."
        )

    region_link = (
        session.query(SuiteSucursalRegionAssignmentORM.id)
        .filter(
            SuiteSucursalRegionAssignmentORM.sucursal_id == branch.sucursal_id,
        )
        .first()
    )
    if region_link is not None:
        raise DemoEnvironmentError(
            "ULTRA DEMO tiene asignación regional. "
            "Una sucursal demo no debe participar en regiones analíticas."
        )


def ensure_demo_branch(session) -> DemoBranchProvisionResult:
    """Crea o valida ULTRA DEMO sin usar IDs mágicos.

    La sucursal se deja ACTIVA para que Tickets, Inventario, PM y Planner la
    traten como una operación real. Su exclusión de BI depende de ``is_demo`` y
    de no crear enlaces a Track/regiones.
    """

    branch = _find_demo_branch(session)
    created = branch is None

    if branch is None:
        branch = Sucursal(
            serie=DEMO_BRANCH_SERIE,
            sucursal=DEMO_BRANCH_NAME,
            estado=DEMO_BRANCH_STATE,
            municipio=DEMO_BRANCH_CITY,
            direccion=DEMO_BRANCH_ADDRESS,
            operational_status=SucursalOperationalStatus.ACTIVA,
            is_demo=True,
            orden_apertura=None,
        )
        session.add(branch)
        session.flush()
    else:
        if not bool(branch.is_demo):
            raise DemoEnvironmentError(
                "La serie DEMO ya existe pero no está marcada como is_demo. "
                "Se requiere revisión manual antes de continuar."
            )

        # El provisionador solo reafirma invariantes; no pisa nombres/direcciones
        # ni la serie si fueron personalizados para una presentación.
        branch.operational_status = SucursalOperationalStatus.ACTIVA
        branch.is_demo = True
        session.flush()

    _assert_demo_isolation(session, branch)

    return DemoBranchProvisionResult(
        sucursal_id=int(branch.sucursal_id),
        sucursal=str(branch.sucursal),
        serie=str(branch.serie),
        created=created,
    )
