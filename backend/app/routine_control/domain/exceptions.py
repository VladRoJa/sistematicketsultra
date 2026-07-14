class RoutineControlMemberError(RuntimeError):
    """Error base del dominio de miembros de Control de Rutinas."""


class RoutineControlMemberIdentityConflict(RoutineControlMemberError):
    """Las identidades primaria y secundaria no describen al mismo miembro."""
