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

@Injectable({ providedIn: 'root' })
export class MaintenancePreventiveService {
  private readonly http = inject(HttpClient);
  private readonly baseUrl =
    \`\${environment.apiUrl}/tickets/preventive-planning\`;

  getContext(): Observable<PreventivePlanningContext> {
    return this.http.get<PreventivePlanningContext>(
      \`\${this.baseUrl}/context\`,
    );
  }

  getEquipment(branchId: number): Observable<{ equipos: PreventiveEquipment[] }> {
    const params = new HttpParams().set('branch_id', String(branchId));
    return this.http.get<{ equipos: PreventiveEquipment[] }>(
      \`\${this.baseUrl}/equipment\`,
      { params },
    );
  }

  listBatches(): Observable<{ batches: PreventiveBatchSummary[] }> {
    return this.http.get<{ batches: PreventiveBatchSummary[] }>(
      \`\${this.baseUrl}/batches\`,
    );
  }

  getBatch(batchId: number): Observable<PreventiveBatch> {
    return this.http.get<PreventiveBatch>(
      \`\${this.baseUrl}/batches/\${batchId}\`,
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
      \`\${this.baseUrl}/batches\`,
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
      \`\${this.baseUrl}/batches/\${batchId}/items\`,
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
      \`\${this.baseUrl}/batches/\${batchId}/items/\${itemId}\`,
      payload,
    );
  }

  deleteItem(batchId: number, itemId: number): Observable<{ mensaje: string }> {
    return this.http.delete<{ mensaje: string }>(
      \`\${this.baseUrl}/batches/\${batchId}/items/\${itemId}\`,
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
      \`\${this.baseUrl}/batches/\${batchId}/validate\`,
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
      \`\${this.baseUrl}/batches/\${batchId}/publish\`,
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
      \`\${this.baseUrl}/imports\`,
      formData,
    );
  }

  downloadTemplate(): Observable<Blob> {
    return this.http.get(
      \`\${this.baseUrl}/template\`,
      { responseType: 'blob' },
    );
  }
}
