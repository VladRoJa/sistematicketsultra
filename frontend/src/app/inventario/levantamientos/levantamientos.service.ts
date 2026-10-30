import { Injectable } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { Observable } from 'rxjs';
import { environment } from 'src/environments/environment';

export type OrigenCorteE4 = 'CSV_HISTORICO' | 'DB_ACTUAL' | 'INICIAL';
export type ResultadoImportacionE4 = 'VALIDATED' | 'INCOMPLETE' | 'INVALID';

export interface ResumenImportacionE4 {
  id: number;
  version: number;
  resultado: ResultadoImportacionE4;
  si: number;
  no: number;
  sin_revisar: number;
  hallazgos: number;
  errores: number;
  avisos: number;
}

export interface LevantamientoResumenE4 {
  id: number;
  cycle_key: string;
  sucursal_id: number;
  estado: string;
  origen_corte: OrigenCorteE4;
  modalidad: 'VERIFICACION' | 'INICIAL';
  responsable: string | null;
  fecha_corte_local: string | null;
  referencias_esperadas: number;
  ultima_importacion_id: number | null;
  importacion_actual: ResumenImportacionE4 | null;
}

export interface LevantamientoE4 {
  id: number;
  cycle_key: string;
  sucursal_id: number;
  estado: string;
  origen_corte: OrigenCorteE4;
  modalidad: 'VERIFICACION' | 'INICIAL';
  responsable: string | null;
  fecha_corte_local: string | null;
  baseline_resumen: { referencias_esperadas: number; excluidas_stock_cero: number; fuente: string };
  baseline_sha256: string | null;
  baseline_capturado_en_utc: string;
  ultima_importacion_id: number | null;
}

export interface DiagnosticoE4 {
  severidad: string;
  codigo: string;
  hoja?: string;
  fila?: number;
  inventario_id?: number;
  detail?: string;
}

export interface ImportacionE4 {
  id: number;
  levantamiento_id: number;
  version: number;
  resultado: ResultadoImportacionE4;
  filename: string;
  file_sha256: string;
  cargado_en_utc: string;
  cargado_por_usuario_id: number;
  control: Record<string, string>;
  resumen: {
    referencias_esperadas: number; si: number; no: number;
    sin_revisar: number; hallazgos: number; provisionales_aparatos: number;
    errores: number; avisos: number;
    revisiones_auto?: {
      nuevas: number; reutilizadas: number; bloqueadas: number;
      e2_creadas: number; auto_revisiones_habilitadas?: boolean;
    };
    pendientes: { inventario_id: number; codigo_original: string; fila_excel: number | null; motivo: string }[];
  };
  diagnosticos: DiagnosticoE4[];
}

export interface FilaE4 {
  hoja: 'APARATOS' | 'HALLAZGOS';
  fila_excel: number;
  inventario_id_declarado: number | null;
  codigo_declarado: string | null;
  respuesta: 'SI' | 'NO' | 'SIN_REVISAR' | null;
  datos_crudos: Record<string, string>;
  diagnosticos: string[];
}

export interface CasoConciliacionE4 {
  caso: string;
  tipo: 'NO' | 'PREFIJO' | 'HALLAZGO' | 'INICIAL';
  inventario_id: number | null;
  fila_excel: number | null;
  codigo: string | null;
  aparato: string | null;
  observacion: string | null;
  resuelto: boolean;
  resolucion: {
    id: number; accion: string; motivo: string;
    solicitud_id: number | null; inventario_id_resultante: number | null;
    actor_usuario_id: number; creado_en_utc: string;
  } | null;
}

export interface TableroConciliacionE4 {
  levantamiento_id: number;
  importacion_id: number | null;
  estado: string;
  version?: number;
  resultado?: ResultadoImportacionE4;
  casos: CasoConciliacionE4[];
  pendientes_respuesta: { inventario_id: number; codigo_original: string; motivo: string }[];
  bloqueos: string[];
  puede_cerrar: boolean;
}

export interface RevisionAutomaticaE4 {
  id: number;
  logical_key: string;
  tipo: string;
  inventario_id: number | null;
  codigo_observado: string | null;
  campo: string | null;
  estado: 'BLOCKED' | 'PENDING' | 'AWAITING_E3' | 'APPROVED' | 'REJECTED' | 'SUPERSEDED';
  motivo_bloqueo: string | null;
  solicitud_e2_id: number | null;
  primera_importacion_id: number;
  ultima_importacion_id: number;
  ultimo_valor: Record<string, unknown>;
}

export interface ListaRevisionesE4 {
  items: RevisionAutomaticaE4[];
  total: number;
  page: number;
  per_page: number;
  resumen: { total: number; bloqueadas: number; por_autorizar: number;
    aprobadas: number; rechazadas: number; superadas: number };
}

@Injectable({ providedIn: 'root' })
export class LevantamientosE4Service {
  private readonly base = environment.apiUrl + '/inventario/levantamientos';

  constructor(private readonly http: HttpClient) {}

  recibirExcel(archivo: File, llave: string): Observable<{
    levantamiento_id: number; importacion: ImportacionE4; replayed: boolean;
  }> {
    const form = new FormData();
    form.append('file', archivo, archivo.name);
    form.append('idempotency_key', llave);
    return this.http.post<{
      levantamiento_id: number; importacion: ImportacionE4; replayed: boolean;
    }>(this.base + '/recepciones', form);
  }

  listar(page: number, sucursalId: number | null): Observable<{
    items: LevantamientoResumenE4[]; total: number; page: number; per_page: number;
  }> {
    let params = new HttpParams().set('page', String(page)).set('per_page', '20');
    if (sucursalId != null) params = params.set('sucursal_id', String(sucursalId));
    return this.http.get<{
      items: LevantamientoResumenE4[]; total: number; page: number; per_page: number;
    }>(this.base, { params });
  }

  crear(sucursalId: number, origen: OrigenCorteE4, cycleKey: string,
        responsable: string, fecha: string, baseline: File | null): Observable<{
    levantamiento: LevantamientoE4; replayed: boolean;
  }> {
    const form = new FormData();
    form.append('sucursal_id', String(sucursalId));
    form.append('origen_corte', origen);
    form.append('cycle_key', cycleKey);
    if (responsable.trim()) form.append('responsable', responsable.trim());
    if (fecha) form.append('fecha_corte_local', fecha);
    if (baseline) form.append('baseline_csv', baseline, baseline.name);
    return this.http.post<{ levantamiento: LevantamientoE4; replayed: boolean }>(this.base, form);
  }

  detalle(id: number): Observable<{ levantamiento: LevantamientoE4; versiones: ImportacionE4[] }> {
    return this.http.get<{ levantamiento: LevantamientoE4; versiones: ImportacionE4[] }>(
      this.base + '/' + id);
  }

  importar(levantamientoId: number, llave: string, archivo: File): Observable<{
    importacion: ImportacionE4; replayed: boolean;
  }> {
    const form = new FormData();
    form.append('idempotency_key', llave);
    form.append('file', archivo, archivo.name);
    return this.http.post<{ importacion: ImportacionE4; replayed: boolean }>(
      this.base + '/' + levantamientoId + '/importaciones', form);
  }

  detalleImportacion(levantamientoId: number, importacionId: number): Observable<{
    importacion: ImportacionE4; filas: FilaE4[];
  }> {
    return this.http.get<{ importacion: ImportacionE4; filas: FilaE4[] }>(
      this.base + '/' + levantamientoId + '/importaciones/' + importacionId);
  }

  original(levantamientoId: number, importacionId: number): Observable<Blob> {
    return this.http.get(this.base + '/' + levantamientoId +
      '/importaciones/' + importacionId + '/archivo', { responseType: 'blob' });
  }
  listarRevisiones(id: number, page = 1): Observable<ListaRevisionesE4> {
    const params = new HttpParams().set('page', String(page)).set('per_page', '20');
    return this.http.get<ListaRevisionesE4>(
      this.base + '/' + id + '/revisiones', { params });
  }

  tablero(id: number): Observable<TableroConciliacionE4> {
    return this.http.get<TableroConciliacionE4>(this.base + '/' + id + '/conciliacion');
  }

  resolver(id: number, data: {
    caso: string; accion: 'E2_APROBADA' | 'REGISTRADO_OFICIAL' | 'BAJA_PREVIA';
    solicitud_id?: number; inventario_id_resultante?: number; movimiento_id?: number;
    motivo: string; idempotency_key: string;
  }): Observable<{ resolucion: { id: number }; replayed: boolean }> {
    return this.http.post<{ resolucion: { id: number }; replayed: boolean }>(
      this.base + '/' + id + '/resoluciones', data);
  }

  cerrar(id: number, motivo: string, key: string): Observable<{
    cierre: { cierre_id: number; estado: string }; replayed: boolean;
  }> {
    return this.http.post<{ cierre: { cierre_id: number; estado: string }; replayed: boolean }>(
      this.base + '/' + id + '/cerrar', { motivo, idempotency_key: key });
  }

}
