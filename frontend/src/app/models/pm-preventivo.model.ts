// src/app/models/pm-preventivo.model.ts

export interface EquipoEstado {
  inventario_id: number;
  codigo_interno: string;
  nombre: string;
  tipo: string;
  marca: string;
  categoria: string;
  sucursal_id: number;
  sucursal: string;
  frecuencia_dias: number;
  ultima_fecha: string | null;
  proxima_fecha: string;
  dias_restantes: number;
  estado: 'ATRASADO' | 'HOY' | 'PROXIMO';
  estado_ejecucion: 'SIN_CAPTURA' | 'CAPTURADO';
  estado_validacion: 'SIN_VALIDACION' | 'PENDIENTE_VALIDACION' | 'VALIDADO' | 'RECHAZADO';
  bitacora_pm_id: number | null;
}

export interface DashboardPm {
  atrasados: EquipoEstado[];
  hoy: EquipoEstado[];
  proximos: EquipoEstado[];
}

export interface RegistrarPmPayload {
  inventario_id: number;
  sucursal_id: number;
  fecha: string;
  resultado: 'OK' | 'FALLA' | 'OBS';
  notas: string;
  checks: Record<string, boolean>;
}

export interface SucursalOption {
  sucursal_id: number;
  sucursal: string;
}

export interface PmBitacoraValidacionDetalle {
  decision: 'VALIDADO' | 'RECHAZADO';
  motivo: string | null;
  validado_por_user_id: number | null;
  validado_en: string | null;
}

export interface PmBitacoraDetalle {
  id: number;
  inventario_id: number;
  sucursal_id: number;
  created_by_user_id: number | null;
  fecha: string | null;
  resultado: 'OK' | 'FALLA' | 'OBS';
  notas: string | null;
  checks: Record<string, boolean>;
  created_at: string | null;
  validacion: PmBitacoraValidacionDetalle | null;
}

export interface PmBitacoraResumen {
  id: number;
  inventario_id: number;
  codigo_interno: string;
  nombre: string;
  sucursal_id: number;
  sucursal: string;
  fecha: string | null;
  resultado: 'OK' | 'FALLA' | 'OBS';
  notas: string | null;
  created_at: string | null;
  created_by_user_id: number | null;
  estado_validacion: 'SIN_VALIDACION' | 'VALIDADO' | 'RECHAZADO';
}

export interface PmConfiguracionResumen {
  id: number;
  inventario_id: number;
  codigo_interno: string;
  nombre: string;
  sucursal_id: number;
  sucursal: string;
  frecuencia_dias: number;
  activo: boolean;
  created_at: string | null;
  updated_at: string | null;
}
