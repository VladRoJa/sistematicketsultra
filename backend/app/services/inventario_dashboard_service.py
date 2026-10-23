"""Indicadores agregados del dashboard de Inventario (solo lectura).

Contrato:
- Una referencia es un par (inventario_id, sucursal_id), no la suma de
  unidades heterogéneas (piezas, cajas, equipos).
- Sin sucursal explícita se excluyen sucursales DEMO, incluso en vista global.
- El stock es actual; el filtro temporal solo afecta actividad y anulaciones.
- Una anulación se cuenta por su fecha real de anulación, no por la fecha
  histórica del movimiento que revirtió.
"""
from datetime import datetime, time, timedelta, timezone

import pytz
from sqlalchemy import func

from app.extensions import db
from app.models.catalogos import CategoriaInventario
from app.models.inventario import (
    InventarioGeneral,
    InventarioSucursal,
    MovimientoInventario,
)
from app.models.sucursal_model import Sucursal
from app.models.user_model import UserORM


TIJUANA = pytz.timezone("America/Tijuana")


def _filtrar_sucursales(query, sucursal_id, ids_autorizados):
    if sucursal_id is not None:
        return query.filter(Sucursal.sucursal_id == sucursal_id)
    if ids_autorizados is not None:
        query = query.filter(Sucursal.sucursal_id.in_(ids_autorizados))
    return query.filter(Sucursal.is_demo.is_(False))


def consultar_resumen_inventario(*, sucursal_id=None, ids_autorizados=None,
                                 periodo_dias=30, fecha_hoy=None):
    """Consultar agregados SQL sin traer todo el inventario al navegador."""
    hoy = fecha_hoy or datetime.now(TIJUANA).date()
    desde = hoy - timedelta(days=periodo_dias - 1)

    # MovimientoInventario.fecha es TIMESTAMP sin zona y guarda hora local.
    inicio_local = datetime.combine(desde, time.min)
    fin_local_exclusivo = datetime.combine(hoy + timedelta(days=1), time.min)

    # La anulación, en cambio, se guarda como TIMESTAMPTZ en UTC.
    inicio_utc = TIJUANA.localize(inicio_local).astimezone(timezone.utc)
    fin_utc = TIJUANA.localize(fin_local_exclusivo).astimezone(timezone.utc)

    sucursales_query = db.session.query(
        Sucursal.sucursal_id,
        Sucursal.sucursal,
    )
    sucursales = _filtrar_sucursales(
        sucursales_query, sucursal_id, ids_autorizados
    ).order_by(Sucursal.sucursal.asc()).all()

    # LEFT JOIN mantiene visibles las sucursales que aún no tienen inventario.
    stock_query = db.session.query(
        Sucursal.sucursal_id,
        func.count(InventarioSucursal.id).filter(
            InventarioSucursal.stock > 0
        ).label("con_stock"),
        func.count(InventarioSucursal.id).filter(
            db.or_(
                InventarioSucursal.stock <= 0,
                InventarioSucursal.stock.is_(None),
            )
        ).label("sin_stock"),
    ).outerjoin(
        InventarioSucursal,
        InventarioSucursal.sucursal_id == Sucursal.sucursal_id,
    )
    stock_query = _filtrar_sucursales(
        stock_query, sucursal_id, ids_autorizados
    )
    stock_por_sucursal = {
        row.sucursal_id: (int(row.con_stock), int(row.sin_stock))
        for row in stock_query.group_by(Sucursal.sucursal_id).all()
    }

    por_sucursal = []
    for id_sucursal, nombre in sucursales:
        con_stock, sin_stock = stock_por_sucursal.get(id_sucursal, (0, 0))
        por_sucursal.append({
            "sucursal_id": id_sucursal,
            "sucursal": nombre,
            "referencias_con_stock": con_stock,
            "referencias_sin_stock": sin_stock,
        })

    categoria = func.coalesce(
        func.nullif(func.trim(CategoriaInventario.nombre), ""),
        func.nullif(func.trim(InventarioGeneral.categoria), ""),
        "Sin categoría",
    )
    categorias_query = db.session.query(
        categoria.label("categoria"),
        func.count(InventarioSucursal.id).label("referencias_con_stock"),
    ).join(
        Sucursal, Sucursal.sucursal_id == InventarioSucursal.sucursal_id,
    ).join(
        InventarioGeneral,
        InventarioGeneral.id == InventarioSucursal.inventario_id,
    ).outerjoin(
        CategoriaInventario,
        CategoriaInventario.id == InventarioGeneral.categoria_inventario_id,
    ).filter(InventarioSucursal.stock > 0)
    categorias_query = _filtrar_sucursales(
        categorias_query, sucursal_id, ids_autorizados
    )
    por_categoria = [
        {"categoria": categoria_nombre, "referencias_con_stock": int(cantidad)}
        for categoria_nombre, cantidad in categorias_query.group_by(
            categoria
        ).order_by(
            func.count(InventarioSucursal.id).desc(), categoria.asc()
        ).all()
    ]

    actividad_query = db.session.query(
        MovimientoInventario.tipo_movimiento,
        func.count(MovimientoInventario.id),
    ).join(
        Sucursal, Sucursal.sucursal_id == MovimientoInventario.sucursal_id,
    ).filter(
        MovimientoInventario.fecha >= inicio_local,
        MovimientoInventario.fecha < fin_local_exclusivo,
        MovimientoInventario.anulado.is_(False),
    )
    actividad_query = _filtrar_sucursales(
        actividad_query, sucursal_id, ids_autorizados
    )
    actividad = dict(actividad_query.group_by(
        MovimientoInventario.tipo_movimiento
    ).all())

    anulaciones_query = db.session.query(
        func.count(MovimientoInventario.id)
    ).join(
        Sucursal, Sucursal.sucursal_id == MovimientoInventario.sucursal_id,
    ).filter(
        MovimientoInventario.anulado.is_(True),
        MovimientoInventario.anulado_en_utc >= inicio_utc,
        MovimientoInventario.anulado_en_utc < fin_utc,
    )
    anulaciones_query = _filtrar_sucursales(
        anulaciones_query, sucursal_id, ids_autorizados
    )
    anulaciones_periodo = int(anulaciones_query.scalar() or 0)

    ultimos_query = db.session.query(
        MovimientoInventario.id,
        MovimientoInventario.fecha,
        MovimientoInventario.tipo_movimiento,
        MovimientoInventario.anulado,
        Sucursal.sucursal_id,
        Sucursal.sucursal,
        UserORM.username,
    ).join(
        Sucursal, Sucursal.sucursal_id == MovimientoInventario.sucursal_id,
    ).outerjoin(
        UserORM, UserORM.id == MovimientoInventario.usuario_id,
    ).filter(
        MovimientoInventario.fecha >= inicio_local,
        MovimientoInventario.fecha < fin_local_exclusivo,
    )
    ultimos_query = _filtrar_sucursales(
        ultimos_query, sucursal_id, ids_autorizados
    )
    recientes = [
        {
            "movimiento_id": row.id,
            "fecha_local": row.fecha.isoformat() if row.fecha else None,
            "tipo": row.tipo_movimiento,
            "estado": "anulado" if row.anulado else "activo",
            "sucursal_id": row.sucursal_id,
            "sucursal": row.sucursal,
            "usuario": row.username or "Desconocido",
        }
        for row in ultimos_query.order_by(
            MovimientoInventario.fecha.desc(),
            MovimientoInventario.id.desc(),
        ).limit(10).all()
    ]

    return {
        "alcance": {
            "sucursal_id": sucursal_id,
            "excluye_demo": sucursal_id is None,
        },
        "periodo": {
            "dias": periodo_dias,
            "desde": desde.isoformat(),
            "hasta": hoy.isoformat(),
            "zona_horaria": "America/Tijuana",
        },
        "indicadores": {
            "referencias_con_stock": sum(
                fila["referencias_con_stock"] for fila in por_sucursal
            ),
            "referencias_sin_stock": sum(
                fila["referencias_sin_stock"] for fila in por_sucursal
            ),
            "entradas_vigentes_periodo": int(actividad.get("entrada", 0)),
            "salidas_vigentes_periodo": int(actividad.get("salida", 0)),
            "anulaciones_periodo": anulaciones_periodo,
        },
        "por_sucursal": por_sucursal,
        "por_categoria": por_categoria,
        "movimientos_recientes": recientes,
        "definiciones": {
            "referencia": "Par inventario-sucursal; no suma unidades de distinta medida",
            "sin_stock": "Referencia asignada con stock cero, negativo o nulo; no incluye artículos nunca asignados",
            "stock": "Existencias actuales, independientes del período seleccionado",
            "movimientos": "Conteo de operaciones no anuladas registradas en el período",
            "anulaciones": "Conteo por fecha de anulación, aunque el movimiento original sea anterior",
            "categorias": "Referencias con stock; un artículo en dos sucursales cuenta en ambas",
        },
    }
