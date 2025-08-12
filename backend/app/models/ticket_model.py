#app\models\ticket_model.py

from datetime import datetime, timezone
import pytz
from app. extensions import db
from app. utils.datetime_utils import format_datetime
from pytz import timezone as tz
from dateutil import parser
from dateutil.parser import isoparse


class Ticket(db.Model):
    __tablename__ = 'tickets'

    id = db.Column(db.Integer, primary_key=True)
    descripcion = db.Column(db.Text, nullable=False)
    username = db.Column(db.String(50), db.ForeignKey('users.username'), nullable=False)
    asignado_a = db.Column(db.String(50), db.ForeignKey('users.username'), nullable=True)
    sucursal_id = db.Column(db.Integer, db.ForeignKey('sucursales.sucursal_id'), nullable=False)
    estado = db.Column(db.Enum('abierto', 'en progreso', 'finalizado', name='estado_ticket_enum'), default='abierto', nullable=False)
    fecha_creacion = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)   
    fecha_finalizado = db.Column(db.DateTime(timezone=True))
    fecha_en_progreso = db.Column(db.DateTime(timezone=True))
    fecha_solucion = db.Column(db.DateTime(timezone=True))
    historial_fechas = db.Column(db.JSON)
    departamento_id = db.Column(db.Integer, db.ForeignKey('departamentos.id'), nullable=True)
    criticidad = db.Column(db.Integer, default=1, nullable=False)
    aparato_id = db.Column(db.Integer, db.ForeignKey('inventario_general.id'), nullable=True)
    problema_detectado = db.Column(db.Text)
    necesita_refaccion = db.Column(db.Boolean, default=False)
    descripcion_refaccion = db.Column(db.Text)
    url_evidencia = db.Column(db.String(500))
    ubicacion = db.Column(db.String(100), nullable=True)
    equipo = db.Column(db.String(100), nullable=True)
    clasificacion_id = db.Column(db.Integer, db.ForeignKey('catalogo_clasificacion.id'), nullable=True)
    categoria = db.Column(db.String(100), nullable=True)
    subcategoria = db.Column(db.String(100), nullable=True)
    detalle = db.Column(db.String(100), nullable=True)
    sucursal_id_destino = db.Column(db.Integer, db.ForeignKey('sucursales.sucursal_id'), nullable=False)

    

    
    
    # ─── Relaciones ──────────────────────────────
    departamento = db.relationship('Departamento', backref='tickets', foreign_keys=[departamento_id])
    usuario = db.relationship('UserORM', foreign_keys=[username])
    sucursal = db.relationship('Sucursal', backref='tickets', foreign_keys=[sucursal_id])
    inventario = db.relationship('InventarioGeneral', foreign_keys=[aparato_id])
    clasificacion = db.relationship('CatalogoClasificacion', backref='tickets')
    sucursal_destino = db.relationship('Sucursal', foreign_keys=[sucursal_id_destino], backref='tickets_destino')

    

    # ─── Serialización ──────────────────────────

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
            'clasificacion_id': self.clasificacion_id,
            'clasificacion_nombre': self.clasificacion.nombre if self.clasificacion else None,
            'jerarquia_clasificacion': self._obtener_jerarquia_clasificacion(),
            'fecha_finalizado': format_datetime(self.fecha_finalizado),
            'fecha_solucion': self.fecha_solucion.isoformat() if self.fecha_solucion else None,
            'necesita_refaccion': self.necesita_refaccion,
            'descripcion_refaccion': self.descripcion_refaccion,
            'problema_detectado': self.problema_detectado,
            'historial_fechas': [
                        {**item} for item in self.historial_fechas or [] if isinstance(item, dict)
                    ],
            'url_evidencia': self.url_evidencia,
            'inventario': {
                'id': self.inventario.id if self.inventario else None,
                'nombre': self.inventario.nombre if self.inventario else None,
                'categoria': self.inventario.categoria if self.inventario else None,
                'marca': self.inventario.marca if self.inventario else None,
                'codigo_interno': self.inventario.codigo_interno if self.inventario else None, 
            } if self.inventario else None,
            'ubicacion': self.ubicacion,
            'equipo': self.equipo,
            'sucursal_id_destino': self.sucursal_id_destino, 
        }
        
        
    # ─── Métodos CRUD ───────────────────────────────────────
    @classmethod
    def create_ticket(cls, descripcion, username, sucursal_id, sucursal_id_destino, departamento_id, criticidad, clasificacion_id, categoria=None, subcategoria=None, detalle=None, aparato_id=None, problema_detectado=None, necesita_refaccion=False, descripcion_refaccion=None, url_evidencia=None, ubicacion=None, equipo=None):
        ticket = cls(
            descripcion=descripcion,
            username=username,
            sucursal_id=sucursal_id,
            sucursal_id_destino=sucursal_id_destino,
            departamento_id=departamento_id,
            criticidad=criticidad,
            clasificacion_id=clasificacion_id,
            categoria=categoria,
            subcategoria=subcategoria,
            detalle=detalle,
            aparato_id=aparato_id,
            problema_detectado=problema_detectado,
            necesita_refaccion=necesita_refaccion,
            descripcion_refaccion=descripcion_refaccion,
            estado='abierto',
            fecha_creacion=datetime.now(timezone.utc),  # ⏰ Guardar en UTC
            url_evidencia=url_evidencia,
            ubicacion=ubicacion,
            equipo=equipo,
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

    def _obtener_jerarquia_clasificacion(self):
        jerarquia = []
        nodo = self.clasificacion
        while nodo:
            jerarquia.insert(0, nodo.nombre)
            nodo = nodo.padre
        return jerarquia