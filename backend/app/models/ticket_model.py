# backend\app\models\ticket_model.py

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
    categoria_inventario_id = db.Column(db.Integer, db.ForeignKey('catalogo_categoria_inventario.id'), nullable=True)
    

    
    
    # ─── Relaciones ──────────────────────────────
    departamento = db.relationship('Departamento', backref='tickets', foreign_keys=[departamento_id])
    usuario = db.relationship('UserORM', foreign_keys=[username])
    sucursal = db.relationship('Sucursal', backref='tickets', foreign_keys=[sucursal_id])
    inventario = db.relationship('InventarioGeneral', foreign_keys=[aparato_id])
    clasificacion = db.relationship('CatalogoClasificacion', backref='tickets')
    sucursal_destino = db.relationship('Sucursal', foreign_keys=[sucursal_id_destino], backref='tickets_destino')
    categoria_inventario = db.relationship('CategoriaInventario', foreign_keys=[categoria_inventario_id])
    

    # ─── Serialización ──────────────────────────

    @staticmethod
    def is_isoformat(value: str) -> bool:
        try:
            isoparse(value)
            return True
        except Exception:
            return False
        
    def _obtener_jerarquia_categoria_inv(self):
        ruta = []
        nodo = self.categoria_inventario
        while nodo:
            ruta.insert(0, nodo.nombre)
            nodo = nodo.padre
        return ruta    



    def to_dict(self):
        import pytz
        from datetime import datetime

        TZ = pytz.timezone("America/Tijuana")

        def safe_dt_iso(dt):
            if not dt:
                return None
            if isinstance(dt, str):
                return dt
            if getattr(dt, "tzinfo", None) is None:
                dt = pytz.utc.localize(dt)
            return dt.astimezone(TZ).isoformat()

        # 1) Elegir árbol según disponibilidad: inventario > clasificación de tickets
        if self.categoria_inventario:
            ruta = self._obtener_jerarquia_categoria_inv() or []
        else:
            ruta = self._obtener_jerarquia_clasificacion() or []

        # 2) Tomar los últimos 3 niveles como cat/sub/det, tolerando vacíos
        tail = [x for x in (ruta[-3:] if ruta else []) if x]
        # rellena hasta 3 posiciones con None para evitar IndexError
        cat_resuelta, subcat_resuelta, detalle_resuelto = (tail + [None, None, None])[:3]

        return {
            'id': self.id,
            'descripcion': self.descripcion,
            'username': self.username,
            'estado': self.estado,

            'fecha_creacion':   safe_dt_iso(self.fecha_creacion),
            'fecha_en_progreso': safe_dt_iso(self.fecha_en_progreso),
            'fecha_finalizado': safe_dt_iso(self.fecha_finalizado),
            'fecha_solucion':   safe_dt_iso(self.fecha_solucion),

            'sucursal_id': self.sucursal_id,
            'departamento_id': self.departamento_id,
            'departamento_nombre': self.departamento.nombre if self.departamento else "N/A",

            'criticidad': self.criticidad,
            'clasificacion_id': self.clasificacion_id,
            'clasificacion_nombre': self.clasificacion and self.clasificacion.nombre,
            'jerarquia_clasificacion': self._obtener_jerarquia_clasificacion(),

            'historial_fechas': [
                {**item} for item in (self.historial_fechas or []) if isinstance(item, dict)
            ],

            # anidación final (texto si existe, None si no)
            'categoria':   cat_resuelta,
            'subcategoria': subcat_resuelta,
            'detalle':     detalle_resuelto,

            'inventario': {
                'id': self.inventario.id if self.inventario else None,
                'nombre': self.inventario and self.inventario.nombre,
                'categoria': self.inventario and self.inventario.categoria,
                'marca': self.inventario and self.inventario.marca,
                'codigo_interno': self.inventario and self.inventario.codigo_interno,
                'subcategoria': self.inventario and self.inventario.subcategoria,
            } if self.inventario else None,

            'ubicacion': self.ubicacion,
            'equipo': self.equipo,
            'sucursal_id_destino': self.sucursal_id_destino,
            'categoria_inventario_id': self.categoria_inventario_id,
            "necesita_refaccion": bool(self.necesita_refaccion),
            "descripcion_refaccion": self.descripcion_refaccion or None,
        }


        
        
    # ─── Métodos CRUD ───────────────────────────────────────
    @classmethod
    def create_ticket(cls, descripcion, username, sucursal_id, sucursal_id_destino, departamento_id, criticidad, clasificacion_id, categoria=None, subcategoria=None, detalle=None, aparato_id=None, problema_detectado=None, necesita_refaccion=False, descripcion_refaccion=None, url_evidencia=None, ubicacion=None, equipo=None):
        
            # 🔹 Sanitizar: si llega un número como texto, lo consideramos vacío (derivaremos la ruta)
        def _clean_text(v):
            if v is None:
                return None
            s = str(v).strip()
            return None if not s or s.isdigit() else s

        categoria = _clean_text(categoria)
        subcategoria = _clean_text(subcategoria)
        detalle = _clean_text(detalle)
            
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
        db.session.flush()
        
        # 👇 NUEVO: si viene de inventario, copiar el leaf del catálogo de inventario
        if aparato_id and not ticket.categoria_inventario_id:
            inv = ticket.inventario  # relación ya definida
            if inv and getattr(inv, 'categoria_inventario_id', None):
                ticket.categoria_inventario_id = inv.categoria_inventario_id
                
        # ✅ NUEVO: si ya hay categoria_inventario_id, poblar textos desde el árbol de inventario
        if ticket.categoria_inventario_id and (not ticket.categoria or not ticket.subcategoria or not ticket.detalle):
            ruta = ticket._obtener_jerarquia_categoria_inv() or []
            tail = ruta[-3:]
            if len(tail) == 1:
                cat, sub, det = tail[0], None, None
            elif len(tail) == 2:
                cat, sub, det = tail[0], tail[1], None
            else:
                cat, sub, det = tail[0], tail[1], tail[2]

            if not ticket.categoria:
                ticket.categoria = cat
            if not ticket.subcategoria:
                ticket.subcategoria = sub
            if not ticket.detalle:
                ticket.detalle = det

        # ── NUEVO: si hay clasificacion, rellenar categoria/subcategoria/detalle desde la jerarquía
        def _es_vacio_o_num(v):
            if v is None:
                return True
            if isinstance(v, str):
                s = v.strip()
                return s == "" or s.isdigit()
            return False

        if (not ticket.categoria_inventario_id) and ticket.clasificacion_id and (_es_vacio_o_num(categoria) or not subcategoria or not detalle):
            # Cargar relación y obtener ruta [raiz ... hoja]
            ruta = ticket._obtener_jerarquia_clasificacion() or []
            if ruta:
                # Tomar los últimos 3 niveles para mostrar cerca de la hoja
                tail = ruta[-3:]
                # Normalizar a 3 slots
                if len(tail) == 1:
                    cat, sub, det = tail[0], None, None
                elif len(tail) == 2:
                    cat, sub, det = tail[0], tail[1], None
                else:
                    cat, sub, det = tail[0], tail[1], tail[2]

                if _es_vacio_o_num(ticket.categoria):
                    ticket.categoria = cat
                if not ticket.subcategoria:
                    ticket.subcategoria = sub
                if not ticket.detalle:
                    ticket.detalle = det

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