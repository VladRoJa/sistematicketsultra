from datetime import datetime, timezone
import pytz
from app.extensions import db
from app.utils.datetime_utils import format_datetime
from pytz import timezone as tz
from dateutil import parser
from dateutil.parser import isoparse


class Ticket(db.Model):
    __tablename__ = 'tickets'

    # ─── Campos ───────────────────────────────────────────────
    id = db.Column(db.Integer, primary_key=True)
    descripcion = db.Column(db.Text, nullable=False)
    username = db.Column(db.String(50), db.ForeignKey('users.username'), nullable=False)
    asignado_a = db.Column(db.String(50), db.ForeignKey('users.username'), nullable=True)
    sucursal_id = db.Column(db.Integer, db.ForeignKey('sucursales.sucursal_id'), nullable=False)
    estado = db.Column(db.Enum('abierto', 'en progreso', 'finalizado'), default='abierto', nullable=False)
    fecha_creacion=datetime.now(tz('America/Tijuana')).astimezone(timezone.utc)    
    fecha_finalizado = db.Column(db.DateTime(timezone=True))
    fecha_en_progreso = db.Column(db.DateTime(timezone=True))
    fecha_solucion = db.Column(db.DateTime(timezone=True))
    historial_fechas = db.Column(db.JSON)
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

    # ─── Relaciones ────────────────────────────────────────
    departamento = db.relationship('Departamento', backref='tickets', foreign_keys=[departamento_id])
    usuario = db.relationship('UserORM', foreign_keys=[username])
    sucursal = db.relationship('Sucursal', backref='tickets', foreign_keys=[sucursal_id])

    # ─── Serialización ───────────────────────────────────────

    @staticmethod
    def is_isoformat(value: str) -> bool:
        try:
            isoparse(value)
            return True
        except Exception:
            return False

    def to_dict(self):
        def format_fecha_corta(dt: datetime | None) -> str:
            return dt.astimezone(pytz.timezone("America/Tijuana")).strftime('%d/%m/%y') if dt else "N/A"

        return {
            'id': self.id,
            'descripcion': self.descripcion,
            'username': self.username,
            'estado': self.estado,
            'fecha_creacion': format_datetime(self.fecha_creacion),
            'sucursal_id': self.sucursal_id,
            'departamento_id': self.departamento_id,
            'departamento_nombre': self.departamento.nombre if self.departamento else "N/A",
            'fecha_en_progreso': format_datetime(self.fecha_en_progreso),
            'criticidad': self.criticidad,
            'categoria': self.categoria,
            'subcategoria': self.subcategoria,
            'subsubcategoria': self.subsubcategoria,
            'fecha_finalizado': format_datetime(self.fecha_finalizado),
            'fecha_solucion': format_fecha_corta(self.fecha_solucion),
            'necesita_refaccion': self.necesita_refaccion,
            'descripcion_refaccion': self.descripcion_refaccion,
            'problema_detectado': self.problema_detectado,
            'historial_fechas': [
                {
                    'fecha': format_fecha_corta(isoparse(item['fecha']).astimezone(pytz.timezone("America/Tijuana")))
                    if self.is_isoformat(item.get('fecha')) else item.get('fecha', 'N/A'),
                    'cambiadoPor': item.get('cambiadoPor', 'N/A'),
                    'fechaCambio': format_fecha_corta(isoparse(item['fechaCambio']).astimezone(pytz.timezone("America/Tijuana")))
                    if self.is_isoformat(item.get('fechaCambio')) else item.get('fechaCambio', 'N/A')
                }
                for item in self.historial_fechas or []
                if isinstance(item, dict)
            ],
            'url_evidencia': self.url_evidencia,
        }

    # ─── Métodos CRUD ───────────────────────────────────────
    @classmethod
    def create_ticket(cls, descripcion, username, sucursal_id, departamento_id, criticidad, categoria, subcategoria=None, subsubcategoria=None, aparato_id=None, problema_detectado=None, necesita_refaccion=False, descripcion_refaccion=None):
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
            estado='abierto',
            fecha_creacion=datetime.now(timezone.utc)  # ⏰ Guardar en UTC
        )
        db.session.add(ticket)
        db.session.commit()
        return ticket

    @classmethod
    def update_ticket_status(cls, ticket_id, nuevo_estado, criticidad=None, categoria=None):
        ticket = cls.query.get(ticket_id)
        if not ticket:
            return None

        now_utc = datetime.now(timezone.utc)

        if nuevo_estado == 'en progreso':
            ticket.fecha_en_progreso = now_utc
        if nuevo_estado == 'finalizado':
            ticket.fecha_finalizado = now_utc

        ticket.estado = nuevo_estado
        if criticidad is not None:
            ticket.criticidad = criticidad
        if categoria is not None:
            ticket.categoria = categoria

        db.session.commit()
        return ticket

    @classmethod
    def get_by_id(cls, ticket_id):
        return cls.query.get(ticket_id)

    def __repr__(self):
        return f"<Ticket {self.id} - {self.estado}>"
