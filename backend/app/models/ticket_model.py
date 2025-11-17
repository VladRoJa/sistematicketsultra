# backend/app/models/ticket_model.py

from datetime import datetime, timezone
import pytz
from app.extensions import db
from app.utils.datetime_utils import format_datetime
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
    sucursal_id_destino = db.Column(db.Integer, db.ForeignKey('sucursales.sucursal_id'), nullable=False)

    # Estado principal del ticket (no lo rompemos)
    estado = db.Column(
        db.Enum('abierto', 'en progreso', 'finalizado', name='estado_ticket_enum'),
        default='abierto',
        nullable=False
    )

    # Fechas operativas
    fecha_creacion = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    fecha_finalizado = db.Column(db.DateTime(timezone=True))
    fecha_en_progreso = db.Column(db.DateTime(timezone=True))
    fecha_solucion = db.Column(db.DateTime(timezone=True))

    # Historial flexible
    historial_fechas = db.Column(db.JSON)

    # Clasificación / contexto
    departamento_id = db.Column(db.Integer, db.ForeignKey('departamentos.id'), nullable=True)
    criticidad = db.Column(db.Integer, default=1, nullable=False)
    aparato_id = db.Column(db.Integer, db.ForeignKey('inventario_general.id'), nullable=True)
    problema_detectado = db.Column(db.Text)

    # Refacciones
    necesita_refaccion = db.Column(db.Boolean, default=False)
    descripcion_refaccion = db.Column(db.Text)
    refaccion_definida_por_jefe = db.Column(db.Boolean, default=False)
    
    # Costos y notas de cierre
    costo_solucion = db.Column(db.Numeric(10, 2))
    notas_cierre = db.Column(db.Text)

    # Adjuntos / extras
    url_evidencia = db.Column(db.String(500))
    ubicacion = db.Column(db.String(100), nullable=True)
    equipo = db.Column(db.String(100), nullable=True)

    # Jerarquía (catálogo de tickets)
    clasificacion_id = db.Column(db.Integer, db.ForeignKey('catalogo_clasificacion.id'), nullable=True)
    categoria = db.Column(db.String(100), nullable=True)
    subcategoria = db.Column(db.String(100), nullable=True)
    detalle = db.Column(db.String(100), nullable=True)

    # Árbol de inventario
    categoria_inventario_id = db.Column(db.Integer, db.ForeignKey('catalogo_categoria_inventario.id'), nullable=True)

    # ──────────────── NUEVO: Flujo de pre-aprobación RRHH ────────────────
    # Si el ticket es de RRHH, primero debe aprobar el gerente general/regional.
    requiere_aprobacion = db.Column(db.Boolean, default=True)  # banderita de entrada
    aprobacion_estado = db.Column(db.String(20))                # 'pendiente' | 'aprobado' | 'rechazado' | None
    aprobacion_fecha = db.Column(db.DateTime(timezone=True))
    aprobador_username = db.Column(db.String(50))
    aprobacion_comentario = db.Column(db.Text)

    # ──────────────── NUEVO: Doble check de cierre ────────────────
    # Secuencia: jefe de departamento aprueba → creador confirma (conformidad).
    # Si cualquiera rechaza, vuelve a “en progreso” con nueva fecha compromiso.
    estado_cierre = db.Column(db.String(30))  # 'pendiente_jefe'|'pendiente_creador'|'rechazado_por_jefe'|'rechazado_por_creador'|None
    motivo_rechazo_cierre = db.Column(db.Text)

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

    def _obtener_jerarquia_clasificacion(self):
        jerarquia = []
        nodo = self.clasificacion
        while nodo:
            jerarquia.insert(0, nodo.nombre)
            nodo = nodo.padre
        return jerarquia

    def to_dict(self):
        import pytz
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
        cat_resuelta, subcat_resuelta, detalle_resuelto = (tail + [None, None, None])[:3]

        return {
            'id': self.id,
            'descripcion': self.descripcion,
            'username': self.username,
            'asignado_a': self.asignado_a,
            'estado': self.estado,

            'fecha_creacion':   safe_dt_iso(self.fecha_creacion),
            'fecha_en_progreso': safe_dt_iso(self.fecha_en_progreso),
            'fecha_finalizado': safe_dt_iso(self.fecha_finalizado),
            'fecha_solucion':   safe_dt_iso(self.fecha_solucion),

            'sucursal_id': self.sucursal_id,
            'sucursal_id_destino': self.sucursal_id_destino,

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
            'categoria_inventario_id': self.categoria_inventario_id,

            "necesita_refaccion": bool(self.necesita_refaccion),
            "descripcion_refaccion": self.descripcion_refaccion or None,
            "refaccion_definida_por_jefe": bool(self.refaccion_definida_por_jefe),

            # RRHH approval
            "requiere_aprobacion": bool(self.requiere_aprobacion),
            "aprobacion_estado": self.aprobacion_estado,
            "aprobacion_fecha": safe_dt_iso(self.aprobacion_fecha),
            "aprobador_username": self.aprobador_username,
            "aprobacion_comentario": self.aprobacion_comentario,

            # Doble check de cierre
            "estado_cierre": self.estado_cierre,
            "motivo_rechazo_cierre": self.motivo_rechazo_cierre,
            
            # Costos y notas de cierre
            "costo_solucion": float(self.costo_solucion) if self.costo_solucion is not None else None,
            "notas_cierre": self.notas_cierre,
            
        }

    # ─── Métodos CRUD / helpers ───────────────────────────────────────
    @classmethod
    def create_ticket(cls, descripcion, username, sucursal_id, sucursal_id_destino,
                    departamento_id, criticidad, clasificacion_id,
                    categoria=None, subcategoria=None, detalle=None,
                    aparato_id=None, problema_detectado=None,
                    necesita_refaccion=False, descripcion_refaccion=None,
                    url_evidencia=None, ubicacion=None, equipo=None,
                    # 👇 NUEVO: parámetros opcionales para flujo inicial y RRHH
                    estado: str = 'abierto',
                    requiere_aprobacion: bool = False,
                    aprobacion_estado: str | None = None,
                    aprobador_username: str | None = None,
                    aprobacion_fecha=None,
                    aprobacion_comentario: str | None = None):
        # Sanitizar: si llega un número como texto, lo consideramos vacío (derivaremos la ruta)
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

            # ⏰ Guardar en UTC
            fecha_creacion=datetime.now(timezone.utc),

            url_evidencia=url_evidencia,
            ubicacion=ubicacion,
            equipo=equipo,

            # 👇 NUEVO: aplicar estado inicial y metadatos de aprobación
            estado=estado or 'abierto',
            requiere_aprobacion=bool(requiere_aprobacion),
            aprobacion_estado=aprobacion_estado,
            aprobador_username=aprobador_username,
            aprobacion_fecha=aprobacion_fecha,
            aprobacion_comentario=aprobacion_comentario,
        )
        db.session.add(ticket)
        db.session.flush()
        
        # Si viene por flujo de INVENTARIO, anulamos clasificacion_id (evita "fantasma Edificio")
        if ticket.categoria_inventario_id or ticket.aparato_id:
            ticket.clasificacion_id = None

        # Coherencia departamento-clasificación: si no machea, limpiamos
        if ticket.clasificacion and ticket.departamento_id and ticket.clasificacion.departamento_id != ticket.departamento_id:
            ticket.clasificacion_id = None

        # Si viene de inventario, copiar el leaf del catálogo de inventario
        if aparato_id and not ticket.categoria_inventario_id:
            inv = ticket.inventario
            if inv and getattr(inv, 'categoria_inventario_id', None):
                ticket.categoria_inventario_id = inv.categoria_inventario_id

        # Si hay categoria_inventario_id, poblar textos desde el árbol de inventario
        if ticket.categoria_inventario_id and (not ticket.categoria or not ticket.subcategoria or not ticket.detalle):
            ruta = ticket._obtener_jerarquia_categoria_inv() or []
            tail = ruta[-3:]
            if len(tail) == 1:
                cat, sub, det = tail[0], None, None
            elif len(tail) == 2:
                cat, sub, det = tail[0], tail[1], None
            else:
                cat, sub, det = tail[0], tail[1], tail[2]
            ticket.categoria = ticket.categoria or cat
            ticket.subcategoria = ticket.subcategoria or sub
            ticket.detalle = ticket.detalle or det

        # Si hay clasificacion, rellenar categoria/subcategoria/detalle desde la jerarquía
        def _es_vacio_o_num(v):
            if v is None:
                return True
            if isinstance(v, str):
                s = v.strip()
                return s == "" or s.isdigit()
            return False

        if (not ticket.categoria_inventario_id) and ticket.clasificacion_id and (_es_vacio_o_num(categoria) or not subcategoria or not detalle):
            ruta = ticket._obtener_jerarquia_clasificacion() or []
            if ruta:
                tail = ruta[-3:]
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


    # ───────────────────────────────────────────────────────────
    # Helpers de PRE-APROBACIÓN RRHH
    # ───────────────────────────────────────────────────────────
    def marcar_para_aprobacion_rrhh(self, aprobador_username: str = None):
        if self.aprobacion_estado == 'aprobado':
            return  # ya está aprobado, no lo pongas pendiente otra vez
        self.requiere_aprobacion = True
        self.aprobacion_estado = 'pendiente'
        self.aprobador_username = aprobador_username
        self.aprobacion_fecha = None
        self.aprobacion_comentario = None
        db.session.commit()


    def aprobar_rrhh(self, aprobador_username: str, comentario: str = None):
        self.aprobacion_estado = 'aprobado'
        self.aprobacion_fecha = datetime.now(timezone.utc)
        self.aprobador_username = aprobador_username
        self.aprobacion_comentario = comentario
        db.session.commit()

    def rechazar_rrhh(self, aprobador_username: str, comentario: str = None):
        self.aprobacion_estado = 'rechazado'
        self.aprobacion_fecha = datetime.now(timezone.utc)
        self.aprobador_username = aprobador_username
        self.aprobacion_comentario = comentario
        # Opcional: mandar a "abierto" y limpiar fecha_en_progreso
        self.estado = 'abierto'
        self.fecha_en_progreso = None
        db.session.commit()

    # ───────────────────────────────────────────────────────────
    # Helpers de DOBLE CHECK DE CIERRE
    # ───────────────────────────────────────────────────────────
    def solicitar_cierre(self):
        """El JEFE inicia proceso de cierre; queda pendiente conformidad del creador.

        Aquí fijamos la fecha_finalizado como el momento en que el jefe considera
        el ticket terminado, aunque todavía falte la conformidad del creador.
        """
        from datetime import datetime, timezone

        self.estado_cierre = 'pendiente_creador'
        # Siempre fijamos la fecha de finalizado al momento del clic del jefe
        self.fecha_finalizado = datetime.now(timezone.utc)

        db.session.commit()



    def aprobar_cierre_jefe(self):
        """Jefe valida y pasa a conformidad del creador."""
        self.estado_cierre = 'pendiente_creador'
        db.session.commit()

    def rechazar_cierre_jefe(self, motivo: str = None, nueva_fecha_compromiso: datetime | None = None):
        """
        Jefe rechaza: devolvemos a 'en progreso' y reabrimos compromiso.
        """
        self.estado_cierre = 'rechazado_por_jefe'
        self.motivo_rechazo_cierre = motivo
        self.estado = 'en progreso'

        # Al reabrir, la fecha_finalizado ya no es válida
        self.fecha_finalizado = None

        if nueva_fecha_compromiso:
            # Usamos fecha_solucion como 'compromiso'
            self.fecha_solucion = nueva_fecha_compromiso.astimezone(timezone.utc)

        db.session.commit()


    def aceptar_conformidad_creador(self):
        """El creador confirma el cierre y el ticket pasa a 'finalizado'."""
        from datetime import datetime, timezone

        self.estado_cierre = None
        self.motivo_rechazo_cierre = None
        self.estado = 'finalizado'

        # Si el jefe ya fijó fecha_finalizado antes, la respetamos.
        # Solo si viene vacío, la ponemos ahora.
        if not self.fecha_finalizado:
            self.fecha_finalizado = datetime.now(timezone.utc)

        db.session.commit()


    def rechazar_conformidad_creador(self, motivo: str = None, nueva_fecha_compromiso: datetime | None = None):
        """
        El creador rechaza el cierre: reabrimos y pedimos nueva fecha compromiso.
        """
        self.estado_cierre = 'rechazado_por_creador'
        self.motivo_rechazo_cierre = motivo
        self.estado = 'en progreso'

        # Al reabrir por rechazo del creador, la fecha_finalizado deja de ser válida
        self.fecha_finalizado = None

        if nueva_fecha_compromiso:
            self.fecha_solucion = nueva_fecha_compromiso.astimezone(timezone.utc)

        db.session.commit()

