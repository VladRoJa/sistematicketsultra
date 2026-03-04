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
