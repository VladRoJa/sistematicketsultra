from datetime import datetime
import pytz
from app.extensions import db
from app.utils.datetime_utils import format_datetime_short, format_datetime_long

# ─────────────────────────────────────────────────────────
# MODELO: TICKET
# ─────────────────────────────────────────────────────────

class Ticket(db.Model):
    __tablename__ = 'tickets'

    # ─── Campos ───────────────────────────────────────────────
    id = db.Column(db.Integer, primary_key=True)
    descripcion = db.Column(db.Text, nullable=False)
    username = db.Column(db.String(50), db.ForeignKey('users.username'), nullable=False)
    asignado_a = db.Column(db.String(50), db.ForeignKey('users.username'), nullable=True)
    sucursal_id = db.Column(db.Integer, db.ForeignKey('sucursales.sucursal_id'), nullable=False)
    estado = db.Column(db.Enum('abierto', 'en progreso', 'finalizado'), default='abierto', nullable=False)
    fecha_creacion = db.Column(db.DateTime, default=db.func.now(), nullable=False)
    fecha_finalizado = db.Column(db.DateTime)
    departamento = db.relationship('Departamento', backref='tickets', foreign_keys='Ticket.departamento_id')

    departamento_id = db.Column(db.Integer, db.ForeignKey('departamentos.id'), nullable=True)
    criticidad = db.Column(db.Integer, default=1, nullable=False)
    categoria = db.Column(db.String(255), nullable=False)
    subcategoria = db.Column(db.String(100))
    subsubcategoria = db.Column(db.String(100))
    aparato_id = db.Column(db.Integer, db.ForeignKey('aparatos_gimnasio.id'), nullable=True)
    problema_detectado = db.Column(db.Text)
    necesita_refaccion = db.Column(db.Boolean, default=False)
    descripcion_refaccion = db.Column(db.Text)
    url_evidencia = db.Column(db.String(500))
    historial_fechas = db.Column(db.JSON)
    fecha_solucion = db.Column(db.DateTime)
    fecha_en_progreso = db.Column(db.DateTime)

    # ─── Relaciones ────────────────────────────────────────
    usuario = db.relationship('UserORM', foreign_keys='Ticket.username')
    sucursal = db.relationship('Sucursal', backref='tickets', foreign_keys='Ticket.sucursal_id')

    # ─────────────────────────────────────────────────────────
    # MÉTODOS
    # ─────────────────────────────────────────────────────────

    def to_dict(self):
        return {
            'id': self.id,
            'descripcion': self.descripcion,
            'username': self.username,
            'estado': self.estado,
            'fecha_creacion': format_datetime_short(self.fecha_creacion),
            'sucursal_id': self.sucursal_id,
            'departamento_id': self.departamento_id,
            'departamento_nombre': self.departamento.nombre if self.departamento else "N/A",
            'fecha_en_progreso': format_datetime_short(self.fecha_en_progreso),
            'criticidad': self.criticidad,
            'categoria': self.categoria,
            'subcategoria': self.subcategoria,
            'subsubcategoria': self.subsubcategoria,
            'fecha_finalizado': format_datetime_short(self.fecha_finalizado),
            'fecha_solucion': format_datetime_long(self.fecha_solucion),
            'necesita_refaccion': self.necesita_refaccion,
            'descripcion_refaccion': self.descripcion_refaccion,
            'problema_detectado': self.problema_detectado,
            'historial_fechas': self.historial_fechas,
            'url_evidencia': self.url_evidencia,
        }

    @classmethod
    def create_ticket(cls, descripcion, username, sucursal_id, departamento_id, criticidad, categoria, subcategoria=None, subsubcategoria=None, aparato_id=None, problema_detectado=None, necesita_refaccion=False, descripcion_refaccion=None):
        """Crea y guarda un nuevo ticket."""
        ticket = cls(
            descripcion=descripcion,
            username=username,
            sucursal_id=sucursal_id,
            departamento_id=departamento_id,
            criticidad=criticidad,
            categoria=categoria,
            subcategoria=subcategoria,
            subsubcategoria=subsubcategoria,
            aparato_id=aparato_id,
            problema_detectado=problema_detectado,
            necesita_refaccion=necesita_refaccion,
            descripcion_refaccion=descripcion_refaccion,
            estado='abierto'
        )
        db.session.add(ticket)
        db.session.commit()
        return ticket

    @classmethod
    def update_ticket_status(cls, ticket_id, nuevo_estado, criticidad=None, categoria=None):
        """Actualiza estado, criticidad o categoría de un ticket."""
        ticket = cls.query.get(ticket_id)
        if not ticket:
            return None
        if nuevo_estado == 'en progreso':
            ticket.fecha_en_progreso = datetime.now()
        ticket.estado = nuevo_estado
        if criticidad is not None:
            ticket.criticidad = criticidad
        if categoria is not None:
            ticket.categoria = categoria
        if nuevo_estado == 'finalizado':
            fecha_local = datetime.now()
            ticket.fecha_finalizado = fecha_local
        db.session.commit()
        return ticket

    @classmethod
    def get_by_id(cls, ticket_id):
        """Obtiene un ticket por su ID."""
        return cls.query.get(ticket_id)

    def __repr__(self):
        return f"<Ticket {self.id} - {self.estado}>"
