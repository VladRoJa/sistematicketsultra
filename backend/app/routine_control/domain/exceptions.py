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
