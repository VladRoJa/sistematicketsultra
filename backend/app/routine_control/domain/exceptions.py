class RoutineControlMemberError(RuntimeError):
    """Error base del dominio de miembros de Control de Rutinas."""


class RoutineControlMemberIdentityConflict(RoutineControlMemberError):
    """Las identidades primaria y secundaria no describen al mismo miembro."""


class RoutineControlEvidenceError(RuntimeError):
    """Error base del dominio de evidencias de Control de Rutinas."""


class RoutineControlEvidenceIdentityConflict(RoutineControlEvidenceError):
    """La identidad de evidencia pertenece a otro miembro del proveedor."""


class RoutineControlEvidenceValidationError(RoutineControlEvidenceError):
    """El comando de evidencia no cumple las reglas mínimas de ingreso."""


class RoutineControlMemberEvidenceError(RuntimeError):
    """Error base de asociaciones socio-evidencia de Control de Rutinas."""


class RoutineControlMemberEvidenceValidationError(
    RoutineControlMemberEvidenceError
):
    """El comando de asociación no cumple sus reglas de validación."""


class RoutineControlMemberEvidenceNotFound(RoutineControlMemberEvidenceError):
    """No existe una entidad o asociación requerida por la operación."""


class RoutineControlMemberEvidenceConflict(RoutineControlMemberEvidenceError):
    """El estado actual de la asociación impide la operación solicitada."""
