import { Injectable } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { Observable } from 'rxjs';

import { environment } from '../../../environments/environment';

export type TrackTiendaGenerationMode = 'manual_preview' | 'official_closed_day';

export interface TrackTiendaResolvedVersion {
  id: number;
  version_type: string;
  status: string;
  generated_at_utc: string | null;
  finished_at_utc: string | null;
}

export interface TrackTiendaSummary {
  track_total: number;
  composition_total: number;
  difference: number;
  is_reconciled: boolean;
  target_total: number;
  progress_pct: number;
  cantidad_total: number;
  operaciones: number;
  ticket_promedio: number;
  top_clave_producto: string | null;
  top_producto: string | null;
  top_sucursal: string | null;
}

export interface TrackTiendaCompositionItem {
  clave_producto: string;
  total: number;
  cantidad: number;
  operaciones: number;
  participacion_pct: number;
  ticket_promedio: number;
}

export interface TrackTiendaProductItem extends TrackTiendaCompositionItem {
  descripcion: string;
}

export interface TrackTiendaBranchItem {
  sucursal_canon: string;
  total: number;
  cantidad: number;
  operaciones: number;
  participacion_pct: number;
  ticket_promedio: number;
}

export interface TrackTiendaDailyItem {
  fecha: string;
  total: number;
  cantidad: number;
  operaciones: number;
}

export interface TrackTiendaOperation {
  row_index: number | null;
  fecha: string;
  hora: string;
  sucursal_canon: string;
  sucursal_origen: string;
  folio: string;
  clave: string;
  clave_producto: string;
  descripcion: string;
  cantidad: number;
  precio_unitario: number;
  total: number;
  forma_pago: string;
  estatus: string;
  realizo_venta: string;
  capturista: string;
  socio: string;
}

export interface TrackTiendaDetailFilter {
  clave_producto: string | null;
  descripcion: string | null;
  sucursal_canon: string | null;
}

export interface TrackTiendaCompositionResponse {
  status: 'ok' | 'error';
  message?: string;
  detail?: string;
  track_date: string;
  generation_mode: TrackTiendaGenerationMode;
  resolved_version: TrackTiendaResolvedVersion;
  source_snapshot_id: number;
  summary: TrackTiendaSummary;
  composition: TrackTiendaCompositionItem[];
  products: TrackTiendaProductItem[];
  branches: TrackTiendaBranchItem[];
  daily: TrackTiendaDailyItem[];
  detail_filter: TrackTiendaDetailFilter;
  operation_count: number;
  operation_limit: number;
  operations: TrackTiendaOperation[];
}

export interface TrackTiendaCompositionRequest {
  trackDate: string;
  generationMode: TrackTiendaGenerationMode;
  includeOperations?: boolean;
  claveProducto?: string | null;
  descripcion?: string | null;
  sucursalCanon?: string | null;
  operationLimit?: number;
}

@Injectable({
  providedIn: 'root',
})
export class TrackTiendaCompositionService {
  private readonly apiUrl = `${environment.apiUrl}/track/tienda-composition`;

  constructor(private readonly http: HttpClient) {}

  getComposition(
    request: TrackTiendaCompositionRequest,
  ): Observable<TrackTiendaCompositionResponse> {
    let params = new HttpParams()
      .set('track_date', request.trackDate)
      .set('generation_mode', request.generationMode);

    if (request.includeOperations) {
      params = params.set('include_operations', 'true');
    }

    if (request.claveProducto) {
      params = params.set('clave_producto', request.claveProducto);
    }

    if (request.descripcion) {
      params = params.set('descripcion', request.descripcion);
    }

    if (request.sucursalCanon) {
      params = params.set('sucursal_canon', request.sucursalCanon);
    }

    if (request.operationLimit) {
      params = params.set('operation_limit', String(request.operationLimit));
    }

    return this.http.get<TrackTiendaCompositionResponse>(this.apiUrl, {
      params,
    });
  }
}
