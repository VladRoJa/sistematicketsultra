import { Injectable, inject } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { Observable } from 'rxjs';

import { environment } from 'src/environments/environment';

export interface PreventiveBranch {
  id: number;
  nombre: string;
  is_demo: boolean;
}

export interface PreventiveResponsible {
  user_id: number;
  username: string;
  rol: string;
}

export interface PreventiveEquipment {
  inventario_id: number;
  codigo_interno: string;
  nombre: string;
  marca: string;
  familia_equipo_id: number | null;
  familia: {
    id: number;
    key: string;
    nombre: string;
  } | null;
}

export interface PreventivePlanningContext {
  sucursales: PreventiveBranch[];
  responsables: PreventiveResponsible[];
}

export interface MaintenanceCrew {
  id: number;
  nombre: string;
  region_id: number | null;
  region: string | null;
  activo: boolean;
}

export interface MaintenancePersonnel {
  id: number;
  user_id: number;
  username: string;
  rol: string;
  crew_id: number | null;
  crew: string | null;
  region_id: number | null;
  activo: boolean;
}

export interface MaintenancePersonnelCatalog {
  personnel: MaintenancePersonnel[];
  candidates: Array<{
    user_id: number;
    username: string;
    rol: string;
  }>;
  crews: MaintenanceCrew[];
  regions: Array<{
    id: number;
    key: string;
    label: string;
  }>;
}

export interface PreventiveDraftItem {
  id: number;
  batch_id: number;
  source_row_number: number | null;
  sucursal_input: string | null;
  codigo_equipo_input: string | null;
  responsable_input: string | null;
  fecha_programada_input: string | null;
  sucursal_id: number | null;
  inventario_id: number | null;
  responsable_user_id: number | null;
  fecha_programada: string | null;
  actividad: string | null;
  observaciones: string | null;
  validation_status: 'PENDIENTE' | 'VALIDO' | 'ERROR';
  validation_errors: string[];
  ticket_id: number | null;
}

export interface PreventiveBatch {
  id: number;
  batch_key: string;
  nombre: string;
  source_type: 'MANUAL' | 'ARCHIVO';
  status: 'BORRADOR' | 'PUBLICADO' | 'CANCELADO';
  period_start: string | null;
  period_end: string | null;
  source_filename: string | null;
  source_sha256: string | null;
  notes: string | null;
  created_by_user_id: number | null;
  published_by_user_id: number | null;
  published_at: string | null;
  items: PreventiveDraftItem[];
}

export interface PreventiveBatchSummary {
  id: number;
  batch_key: string;
  nombre: string;
  source_type: 'MANUAL' | 'ARCHIVO';
  status: 'BORRADOR' | 'PUBLICADO' | 'CANCELADO';
  period_start: string | null;
  period_end: string | null;
  created_by_user_id: number | null;
  published_at: string | null;
  total: number;
  validos: number;
  errores: number;
  pendientes: number;
}

export interface PreventiveValidationSummary {
  batch_id: number;
  total: number;
  validos: number;
  errores: number;
  publicable: boolean;
}

export interface MaintenanceMyProgramItem {
  ticket_id: number;
  tipo_mantenimiento: 'PREVENTIVO' | 'CORRECTIVO';
  estado: string;
  operational_status:
    | 'HOY'
    | 'PROGRAMADO'
    | 'VENCIDO'
    | 'PENDIENTE_VALIDACION'
    | 'SIN_FECHA';
  fecha_trabajo: string | null;
  sucursal_id: number | null;
  sucursal: string;
  inventario_id: number | null;
  codigo_equipo: string | null;
  equipo: string;
  actividad: string;
  problema_detectado: string | null;
  necesita_refaccion: boolean;
  descripcion_refaccion: string | null;
}

export interface MaintenanceMyProgram {
  personnel: {
    id: number;
    user_id: number;
    username: string;
    crew_id: number | null;
    crew: string | null;
    region_id: number | null;
  };
  window: {
    start_date: string;
    end_date: string;
    today: string;
  };
  metrics: {
    today: number;
    week: number;
    overdue: number;
    pending_validation: number;
    unscheduled: number;
  };
  today_items: MaintenanceMyProgramItem[];
  week_items: MaintenanceMyProgramItem[];
  overdue: MaintenanceMyProgramItem[];
  pending_validation: MaintenanceMyProgramItem[];
  unscheduled: MaintenanceMyProgramItem[];
}

@Injectable({ providedIn: 'root' })
export class MaintenancePreventiveService {
  private readonly http = inject(HttpClient);
  private readonly baseUrl =
    `${environment.apiUrl}/tickets/preventive-planning`;

  getMyProgram(params?: {
    start_date?: string;
    end_date?: string;
  }): Observable<MaintenanceMyProgram> {
    let httpParams = new HttpParams();

    if (params?.start_date) {
      httpParams = httpParams.set('start_date', params.start_date);
    }
    if (params?.end_date) {
      httpParams = httpParams.set('end_date', params.end_date);
    }

    return this.http.get<MaintenanceMyProgram>(
      `${this.baseUrl}/my-program`,
      { params: httpParams },
    );
  }

  getPersonnelCatalog(): Observable<MaintenancePersonnelCatalog> {
    return this.http.get<MaintenancePersonnelCatalog>(
      `${this.baseUrl}/personnel`,
    );
  }

  createCrew(payload: {
    nombre: string;
    region_id?: number | null;
  }): Observable<MaintenanceCrew> {
    return this.http.post<MaintenanceCrew>(
      `${this.baseUrl}/crews`,
      payload,
    );
  }

  updateCrew(
    crewId: number,
    payload: Partial<{
      nombre: string;
      region_id: number | null;
      activo: boolean;
    }>,
  ): Observable<MaintenanceCrew> {
    return this.http.put<MaintenanceCrew>(
      `${this.baseUrl}/crews/${crewId}`,
      payload,
    );
  }

  createPersonnel(payload: {
    user_id: number;
    crew_id?: number | null;
  }): Observable<{ id: number }> {
    return this.http.post<{ id: number }>(
      `${this.baseUrl}/personnel`,
      payload,
    );
  }

  updatePersonnel(
    personnelId: number,
    payload: Partial<{
      crew_id: number | null;
      activo: boolean;
    }>,
  ): Observable<{ id: number }> {
    return this.http.put<{ id: number }>(
      `${this.baseUrl}/personnel/${personnelId}`,
      payload,
    );
  }

  getContext(): Observable<PreventivePlanningContext> {
    return this.http.get<PreventivePlanningContext>(
      `${this.baseUrl}/context`,
    );
  }

  getEquipment(branchId: number): Observable<{ equipos: PreventiveEquipment[] }> {
    const params = new HttpParams().set('branch_id', String(branchId));
    return this.http.get<{ equipos: PreventiveEquipment[] }>(
      `${this.baseUrl}/equipment`,
      { params },
    );
  }

  listBatches(): Observable<{ batches: PreventiveBatchSummary[] }> {
    return this.http.get<{ batches: PreventiveBatchSummary[] }>(
      `${this.baseUrl}/batches`,
    );
  }

  getBatch(batchId: number): Observable<PreventiveBatch> {
    return this.http.get<PreventiveBatch>(
      `${this.baseUrl}/batches/${batchId}`,
    );
  }

  createBatch(payload: {
    nombre: string;
    source_type: 'MANUAL' | 'ARCHIVO';
    period_start?: string | null;
    period_end?: string | null;
    notes?: string | null;
  }): Observable<PreventiveBatch> {
    return this.http.post<PreventiveBatch>(
      `${this.baseUrl}/batches`,
      payload,
    );
  }

  addItems(
    batchId: number,
    items: Array<{
      sucursal: string;
      codigo_equipo: string;
      responsable: string;
      fecha_programada: string;
      actividad: string;
      observaciones?: string | null;
    }>,
  ): Observable<PreventiveBatch> {
    return this.http.post<PreventiveBatch>(
      `${this.baseUrl}/batches/${batchId}/items`,
      { items },
    );
  }

  updateItem(
    batchId: number,
    itemId: number,
    payload: Partial<{
      sucursal: string;
      codigo_equipo: string;
      responsable: string;
      fecha_programada: string;
      actividad: string;
      observaciones: string | null;
    }>,
  ): Observable<{ mensaje: string; item: { id: number; validation_status: string } }> {
    return this.http.put<{
      mensaje: string;
      item: { id: number; validation_status: string };
    }>(
      `${this.baseUrl}/batches/${batchId}/items/${itemId}`,
      payload,
    );
  }

  deleteItem(batchId: number, itemId: number): Observable<{ mensaje: string }> {
    return this.http.delete<{ mensaje: string }>(
      `${this.baseUrl}/batches/${batchId}/items/${itemId}`,
    );
  }

  validateBatch(batchId: number): Observable<{
    summary: PreventiveValidationSummary;
    batch: PreventiveBatch;
  }> {
    return this.http.post<{
      summary: PreventiveValidationSummary;
      batch: PreventiveBatch;
    }>(
      `${this.baseUrl}/batches/${batchId}/validate`,
      {},
    );
  }

  publishBatch(batchId: number): Observable<{
    mensaje: string;
    ticket_ids: number[];
    batch: PreventiveBatch;
  }> {
    return this.http.post<{
      mensaje: string;
      ticket_ids: number[];
      batch: PreventiveBatch;
    }>(
      `${this.baseUrl}/batches/${batchId}/publish`,
      {},
    );
  }

  importBatch(
    file: File,
    metadata?: {
      nombre?: string;
      period_start?: string;
      period_end?: string;
      notes?: string;
    },
  ): Observable<{
    summary: PreventiveValidationSummary;
    batch: PreventiveBatch;
  }> {
    const formData = new FormData();
    formData.append('file', file, file.name);

    if (metadata?.nombre) {
      formData.append('nombre', metadata.nombre);
    }
    if (metadata?.period_start) {
      formData.append('period_start', metadata.period_start);
    }
    if (metadata?.period_end) {
      formData.append('period_end', metadata.period_end);
    }
    if (metadata?.notes) {
      formData.append('notes', metadata.notes);
    }

    return this.http.post<{
      summary: PreventiveValidationSummary;
      batch: PreventiveBatch;
    }>(
      `${this.baseUrl}/imports`,
      formData,
    );
  }

  downloadTemplate(): Observable<Blob> {
    return this.http.get(
      `${this.baseUrl}/template`,
      { responseType: 'blob' },
    );
  }
}
