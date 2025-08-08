// src/app/models/asistencia-response.model.ts
export interface AsistenciaResponse {
  ok: boolean;
  mensaje: string;
  tipo_marcado?: string;
  hora?: string;
  proxima_checada?: {
    tipo: string;
    hora: string;
  };
  faltantes?: string[];
}
