/**
 * Presentación de cambios de responsable registrada por Tickets V1.
 * No infiere transiciones donde el historial legacy no guarda ambos valores.
 */
export interface CambioResponsableHistorial {
  anterior: string;
  nuevo: string;
}

interface EntradaHistorial {
  tipo?: string | null;
  asignado_anterior?: string | null;
  asignado_nuevo?: string | null;
  tipo_atencion_anterior?: string | null;
  tipo_atencion_nuevo?: string | null;
}

export function esEventoReasignacion(item: EntradaHistorial | null): boolean {
  return item?.tipo === 'maintenance_reassignment_v1';
}

export function esEventoCoordinacion(item: EntradaHistorial | null): boolean {
  return item?.tipo === 'maintenance_coordination_v1';
}

function etiquetaResponsable(
  usuario: string | null | undefined,
  tipoAtencion: string | null | undefined,
): string {
  if (tipoAtencion === 'EXTERNA') return 'Proveedor externo';
  return String(usuario || '').trim() || 'Sin asignar';
}

export function obtenerCambioResponsableHistorial(
  item: EntradaHistorial | null,
): CambioResponsableHistorial | null {
  if (!item || (!esEventoReasignacion(item) && !esEventoCoordinacion(item))) {
    return null;
  }

  const anterior = etiquetaResponsable(
    item.asignado_anterior,
    item.tipo_atencion_anterior,
  );
  const nuevo = etiquetaResponsable(
    item.asignado_nuevo,
    item.tipo_atencion_nuevo,
  );

  if (anterior === nuevo) return null;
  return { anterior, nuevo };
}
