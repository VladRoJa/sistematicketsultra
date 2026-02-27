# app/models/user_model.py

from werkzeug.security import check_password_hash
from sqlalchemy import text
from app.extensions import db

# ─────────────────────────────────────────────────────────────
# MODELO: USUARIO
# ─────────────────────────────────────────────────────────────

class UserORM(db.Model):
    __tablename__ = 'users'

    # ─── Campos ──────────────────────────────────────────────
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), nullable=False, unique=True)
    password = db.Column(db.String(255), nullable=False)
    rol = db.Column(db.String(50), default="usuario", nullable=False)
    sucursal_id = db.Column(db.Integer, db.ForeignKey('sucursales.sucursal_id'), nullable=False)

    # OJO: actualmente no es FK. Si quieres FK real: db.ForeignKey('departamentos.id') + migración.
    department_id = db.Column(db.Integer, nullable=False)

    email = db.Column(db.String(120), unique=True, index=True, nullable=False)

    # ─── Relaciones ─────────────────────────────────────────
    movimientos = db.relationship('MovimientoInventario', backref='usuario', cascade='all, delete-orphan')
    asistencias = db.relationship('RegistroAsistencia', backref='usuario', cascade='all, delete-orphan')

    # ─── Constantes de rol (usadas en permisos) ─────────────
    # Ajusta nombres a los que realmente usas en tu app.
    ROLE_ADMIN              = 'ADMINISTRADOR'
    ROLE_EDITOR_CORP        = 'EDITOR_CORPORATIVO'
    ROLE_GERENTE            = 'GERENTE'
    ROLE_GERENTE_GENERAL    = 'GERENTE_GENERAL'
    ROLE_JEFE_DEPTO         = 'JEFE_DEPARTAMENTO'
    ROLE_USUARIO            = 'USUARIO'
    ROLE_LECTOR_GLOBAL      = 'LECTOR_GLOBAL'

    # ─────────────────────────────────────────────────────────────
    # MÉTODOS
    # ─────────────────────────────────────────────────────────────

    def verify_password(self, password_input):
        return check_password_hash(self.password.strip(), password_input.strip())

    @classmethod
    def get_by_username(cls, username):
        return cls.query.filter(db.func.lower(cls.username) == db.func.lower(username)).first()

    @classmethod
    def get_by_id(cls, user_id):
        """Obtiene un usuario por su ID."""
        return cls.query.filter_by(id=user_id).first()

    # ─── Aliases / Normalizadores ────────────────────────────
    @property
    def rol_norm(self) -> str:
        return (self.rol or '').strip().upper()

    @property
    def departamento_id(self) -> int:
        """Alias consistente para department_id (español)."""
        return self.department_id

    # ─── Permisos de alto nivel (se usan en endpoints) ───────
    def es_admin(self) -> bool:
        return self.rol_norm in {self.ROLE_ADMIN}

    def es_gerente_general(self) -> bool:
        return self.rol_norm in {self.ROLE_GERENTE_GENERAL}

    def es_gerente(self) -> bool:
        return self.rol_norm in {self.ROLE_GERENTE, self.ROLE_GERENTE_GENERAL}

    def es_jefe_depto(self, depto_id: int | None) -> bool:
        """Jefe del departamento indicado (o admin)."""
        if self.es_admin():
            return True
        if depto_id is None:
            return False
        return self.rol_norm == self.ROLE_JEFE_DEPTO and self.department_id == int(depto_id)

    def es_rrhh(self) -> bool:
        """Si este usuario pertenece al depto RRHH (ajusta id según tu catálogo)."""
        # Cambia  <ID_RRHH>  por el id real de tu departamento de RRHH.
        ID_RRHH = 5
        return self.department_id == ID_RRHH

    # ─── Reglas específicas del plan ─────────────────────────
    def puede_definir_refaccion(self, ticket) -> bool:
        """
        Solo Jefe del dpto (o Admin) en estas combinaciones:
        - Mantenimiento → Aparatos
        - Sistemas → Dispositivos
        """
        if not ticket:
            return False

        dep = (getattr(ticket, 'departamento', None) and ticket.departamento.nombre) or getattr(ticket, 'departamento_nombre', None)
        cat = getattr(ticket, 'categoria', None) or (
            ticket.jerarquia_clasificacion[1] if getattr(ticket, 'jerarquia_clasificacion', None) and len(ticket.jerarquia_clasificacion) > 1 else None
        )

        dep_norm = (dep or '').strip().lower()
        cat_norm = (cat or '').strip().lower()

        es_mant_aparatos = (dep_norm == 'mantenimiento' and cat_norm == 'aparatos')
        es_sist_dispositivos = (dep_norm == 'sistemas' and cat_norm == 'dispositivos')

        return (es_mant_aparatos or es_sist_dispositivos) and self.es_jefe_depto(getattr(ticket, 'departamento_id', None))

    def puede_aprobar_rrhh(self) -> bool:
        """
        Permiso para aprobar/rechazar tickets RRHH en estado 'pendiente'.
        Normalmente: Gerente General (o el rol que definas).
        """
        return self.es_gerente_general() or self.es_admin()

    # ─── Sucursales asignadas (M:N) ─────────────────────────
    @property
    def sucursales_ids(self) -> list[int]:
        """IDs de sucursales asignadas al usuario (tabla usuario_sucursal)."""
        rows = db.session.execute(
            text("SELECT sucursal_id FROM usuario_sucursal WHERE user_id = :uid"),
            {"uid": self.id},
        ).fetchall()
        return [r[0] for r in rows]

    def __repr__(self):
        return f"<User {self.username}>"

    @departamento_id.setter
    def departamento_id(self, value: int):
        self.department_id = value
