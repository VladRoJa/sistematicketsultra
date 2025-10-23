// frontend/src/app/types/ticket.ts

/** Estados “core” + compatibles con la UI/acciones */
export type EstadoTicket =
  | 'abierto'
  | 'pendiente'                   // compat: algunos helpers lo usan
  | 'en progreso'
  | 'finalizado'
  | 'en_validacion'               // RRHH: pendiente de aprobación
  | 'pendiente_cierre_jefe'       // 1er check: jefe depto
  | 'pendiente_conformidad_creador' // 2º check: creador
  | 'rechazado_por_creador';

export type AprobacionEstado = 'pendiente' | 'aprobado' | 'rechazado' | null;

export type EstadoCierre =
  | 'pendiente_jefe'
  | 'pendiente_creador'
  | 'aprobado'
  | 'rechazado_por_creador'
  | null;

/** Inventario/Equipo que se muestra en la tabla (Sistemas y Mantenimiento) */
export interface InventarioDTO {
  id: number;
  nombre: string;
  categoria?: string;
  subcategoria?: string | number | null;
  codigo_interno?: string | null;
  tipo?: string | null;
  descripcion?: string | null;
}

/** DTO general de Ticket (para PATCH/lectura). Mantiene campos opcionales amplios. */
export interface TicketDTO {
  id: number;

  // Básicos
  descripcion: string;
  username: string;                // creador
  asignado_a?: string | null;

  // Catálogo jerárquico
  departamento?: string | number;
  departamento_id?: number;
  categoria?: string | number | null;
  subcategoria?: string | number | null;
  detalle?: string | number | null;

  // Sucursal
  sucursal_id?: number;
  sucursal_id_destino?: number | null;
  // (solo para pintar)
  sucursal?: string;

  // Estado/criticidad
  estado: EstadoTicket;
  criticidad?: number;

  // Fechas
  fecha_creacion: string | null;
  fecha_en_progreso?: string | null;
  fecha_solucion?: string | null;
  fecha_finalizado?: string | null;

  // Inventario/Equipo
  inventario?: InventarioDTO | null;
  equipo?: string | null;
  ubicacion?: string | null;

  // Clasificación “plana” auxiliar
  clasificacion_id?: number | null;
  clasificacion_nombre?: string | null;

  // Refacción
  necesita_refaccion?: boolean | null;
  descripcion_refaccion?: string | null;
  refaccion_definida_por_jefe?: boolean | null;

  // Evidencia (preview en modal)
  url_evidencia?: string | null;

  // Aprobaciones RRHH
  requiere_aprobacion?: boolean | null;
  aprobacion_estado?: AprobacionEstado;
  aprobacion_fecha?: string | null;
  aprobador_username?: string | null;
  aprobacion_comentario?: string | null;
  departamento_destino_final?: string | number | null;

  // Doble check de cierre
  estado_cierre?: EstadoCierre;
  motivo_rechazo_cierre?: string | null;

  // Historial (compat con diferentes formas que ya usa tu UI)
  historial_fechas?: Array<{
    accion?: string;
    fecha: string;                 // fecha objetivo o de la acción
    usuario?: string;              // alias genérico
    cambiadoPor?: string;          // compat: helpers usan cambiadoPor
    fechaCambio?: string;          // compat
    motivo?: string | null;
    nueva_fecha_solucion?: string | null;
  }>;

  // Extras abiertos para compatibilidad
  [key: string]: any;
}

/** Payload para fijar/actualizar compromiso (fecha_solucion y refacción) */
export interface SetCompromisoPayload {
  /** ISO: 2025-03-14T07:00:00.000Z (tu backend convierte a UTC) */
  fecha_solucion: string;
  necesita_refaccion?: boolean;
  descripcion_refaccion?: string | null;
  /** Lo manda el modal del Jefe cuando define la refacción */
  refaccion_definida_por_jefe?: boolean;
}

export interface RRHHAccionPayload {
  comentario?: string;
}

/** Rechazos de cierre (Jefe o Creador) con nueva cita/compromiso */
export interface CierreRechazoPayload {
  motivo: string;
  /** ISO */
  nueva_fecha_solucion: string;
}
