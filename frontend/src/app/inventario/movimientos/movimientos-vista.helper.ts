/**
 * Proyección de solo lectura para el historial de movimientos.
 * El endpoint entrega referencias al inventario; la vista enriquece datos
 * con el catálogo disponible, sin modificar la respuesta ni crear movimientos.
 */
export interface ProductoEnMovimiento {
  inventario_id?: number | string;
  id?: number | string;
  cantidad?: number | string;
  unidad_medida?: string | null;
  codigo_interno?: string | null;
  no_equipo?: string | null;
  /** Datos del catálogo al consultar el historial, no snapshot histórico. */
  nombre?: string | null;
  marca?: string | null;
  proveedor?: string | null;
  categoria?: string | null;
}

export interface MovimientoInventarioVista {
  id: number;
  fecha?: string;
  tipo?: string;
  usuario?: unknown;
  usuario_id?: number;
  sucursal?: unknown;
  sucursal_id?: number;
  observaciones?: string | null;
  anulado?: boolean;
  anulado_por_usuario_id?: number | null;
  usuario_anulacion?: string | null;
  anulado_en_utc?: string | null;
  motivo_anulacion?: string | null;
  inventarios?: ProductoEnMovimiento[];
}

export interface ProductoCatalogoMovimiento {
  id: number | string;
  nombre?: string | null;
  marca?: string | null;
  proveedor?: string | null;
  categoria?: string | null;
  codigo_interno?: string | null;
}

export interface ArticuloDetalleMovimiento {
  inventarioId: string;
  nombre: string;
  codigoActual: string;
  marca: string;
  proveedor: string;
  categoria: string;
  cantidad: number | string;
  unidadMedida: string;
}

export function cantidadArticulosMovimiento(mov: MovimientoInventarioVista): number {
  return mov.inventarios?.length ?? 0;
}

export function primerArticuloMovimiento(
  mov: MovimientoInventarioVista,
  catalogo: readonly ProductoCatalogoMovimiento[],
): string {
  const primerArticulo = mov.inventarios?.[0];
  if (!primerArticulo) {
    return 'Sin artículos';
  }

  const id = primerArticulo.inventario_id ?? primerArticulo.id;
  const inventario = catalogo.find(articulo => String(articulo.id) === String(id));
  return inventario?.nombre || primerArticulo.codigo_interno || `Inventario #${id ?? '—'}`;
}

export function detallesMovimiento(
  mov: MovimientoInventarioVista,
  catalogo: readonly ProductoCatalogoMovimiento[],
): ArticuloDetalleMovimiento[] {
  const catalogoPorId = new Map(catalogo.map(articulo => [
    String(articulo.id), articulo,
  ] as const));

  return (mov.inventarios ?? []).map(articulo => {
    const inventarioId = String(articulo.inventario_id ?? articulo.id ?? '—');
    const info = catalogoPorId.get(inventarioId);
    return {
      inventarioId,
      nombre: articulo.nombre || info?.nombre || `Inventario #${inventarioId}`,
      // GET /movimientos entrega el código ACTUAL, no una copia histórica.
      codigoActual: articulo.codigo_interno || info?.codigo_interno || '—',
      marca: articulo.marca || info?.marca || '—',
      proveedor: articulo.proveedor || info?.proveedor || '—',
      categoria: articulo.categoria || info?.categoria || '—',
      cantidad: articulo.cantidad ?? '—',
      unidadMedida: articulo.unidad_medida || '—',
    };
  });
}
