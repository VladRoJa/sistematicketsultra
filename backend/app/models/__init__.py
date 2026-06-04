# app\models\__init__.py

# -------------------------------------------------------------------------------
# MODELOS: Inicialización de Modelos del Sistema
# -------------------------------------------------------------------------------

from .ticket_model import Ticket
from .user_model import UserORM
from .sucursal_model import Sucursal, SucursalOperationalStatus
from .inventario import (
    InventarioGeneral,
    InventarioSucursal,
    MovimientoInventario,
    DetalleMovimiento,
)
from .departamento_model import Departamento
from .formulario_ticket import FormularioTicket, CampoFormulario
from .pm_bitacora import PmBitacoraORM
from .pm_validacion import PmValidacionORM
from .warehouse import (
    WarehouseSourceORM,
    WarehouseFamilyORM,
    WarehouseOperationalRoleORM,
    WarehouseReportTypeORM,
    WarehouseUploadORM,
    WarehouseOperatorORM,
    WarehouseAuditLogORM,
    KpiDesempenoSnapshotORM,
    KpiDesempenoSnapshotRowORM,
    KpiVentasNuevosSociosSnapshotORM,
    KpiVentasNuevosSociosSnapshotRowORM,
    TrackSourceTiendaDailyORM,
    WarehouseCommercialCatalogORM,
)
from .suite_governance import (
    SuiteRegionORM,
    SuiteSucursalRegionAssignmentORM,
    SuiteRegionManagerORM,
)
from .planning_targets import (
    PlanningModelConfigORM,
    PlanningTargetBatchORM,
    PlanningTargetBranchRowORM,
    PlanningTargetAdjustmentORM,
    PlanningTargetApprovalEventORM,
    PlanningOperatorORM,
)
from .internal_documents import (
    InternalDocumentCategoryORM,
    InternalDocumentORM,
    InternalDocumentVersionORM,
    InternalDocumentVisibilityORM,
    InternalDocumentLinkORM,
    InternalDocumentAuditLogORM,
    InternalDocumentStatus,
    InternalDocumentVisibilityMode,
    InternalDocumentVisibilityType,
    InternalDocumentLinkEntityType,
    InternalDocumentLinkRole,
    InternalDocumentAuditAction,
)
from .openings import (
    OpeningAuditAction,
    OpeningAuditLogORM,
    OpeningDependencyType,
    OpeningORM,
    OpeningPhaseORM,
    OpeningPhaseStatus,
    OpeningStatus,
    OpeningTaskDependencyORM,
    OpeningTaskORM,
    OpeningTaskPriority,
    OpeningTaskStatus,
)


# -------------------------------------------------------------------------------
# EXPORTACIONES: Control de qué modelos estarán disponibles al importar app.models
# -------------------------------------------------------------------------------
__all__ = [
    "Ticket",
    "UserORM",
    "Sucursal",
    "InventarioGeneral",
    "InventarioSucursal",
    "MovimientoInventario",
    "DetalleMovimiento",
    "Departamento",
    "FormularioTicket",
    "CampoFormulario",
    "PmBitacoraORM",
    "PmValidacionORM",
    "WarehouseSourceORM",
    "WarehouseFamilyORM",
    "WarehouseOperationalRoleORM",
    "WarehouseReportTypeORM",
    "WarehouseUploadORM",
    "WarehouseOperatorORM",
    "WarehouseAuditLogORM",
    "KpiDesempenoSnapshotORM",
    "KpiDesempenoSnapshotRowORM",
    "KpiVentasNuevosSociosSnapshotORM",
    "KpiVentasNuevosSociosSnapshotRowORM",
    "TrackSourceTiendaDailyORM",
    "WarehouseCommercialCatalogORM",
    "SuiteRegionORM",
    "SuiteSucursalRegionAssignmentORM",
    "SuiteRegionManagerORM",
    "PlanningModelConfigORM",
    "PlanningTargetBatchORM",
    "PlanningTargetBranchRowORM",
    "PlanningTargetAdjustmentORM",
    "PlanningTargetApprovalEventORM",
    "PlanningOperatorORM",
    "InternalDocumentCategoryORM",
    "InternalDocumentORM",
    "InternalDocumentVersionORM",
    "InternalDocumentVisibilityORM",
    "InternalDocumentLinkORM",
    "InternalDocumentAuditLogORM",
    "InternalDocumentStatus",
    "InternalDocumentVisibilityMode",
    "InternalDocumentVisibilityType",
    "InternalDocumentLinkEntityType",
    "InternalDocumentLinkRole",
    "InternalDocumentAuditAction",
    "SucursalOperationalStatus",
    "OpeningAuditAction",
    "OpeningAuditLogORM",
    "OpeningDependencyType",
    "OpeningORM",
    "OpeningPhaseORM",
    "OpeningPhaseStatus",
    "OpeningStatus",
    "OpeningTaskDependencyORM",
    "OpeningTaskORM",
    "OpeningTaskPriority",
    "OpeningTaskStatus",
]