// frontend/src/app/services/inventario.service.ts
import { Injectable } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { Observable } from 'rxjs';
import { environment } from 'src/environments/environment';

export type TipoSolicitudInventario =
  'MASTER_FIELD' | 'QUANTITY_DIFFERENCE' | 'NOT_LOCATED' | 'UNREGISTERED_FIND';

export interface SolicitudCorreccionInput {
  tipo: TipoSolicitudInventario;
  sucursal_id: number;
  motivo: string;
  idempotency_key: string;
  inventario_id?: number;
  campo?: string;
  valor_original?: unknown;
  valor_propuesto?: unknown;
  hallazgo_provisional?: { nombre: string; tipo?: string; marca?: string; codigo_interno?: string };
  fecha_observacion_local?: string;
  evidencia_descriptiva?: string;
}

export interface SolicitudCorreccionInventario {
  id: number;
  tipo: TipoSolicitudInventario;
  estado: 'PENDING' | 'APPROVED' | 'REJECTED';
  sucursal_id: number;
  inventario_id: number | null;
  campo: string | null;
  valor_original: unknown;
  valor_propuesto: unknown;
  hallazgo_provisional: Record<string, string> | null;
  baseline_canonico: Record<string, unknown>;
  motivo: string;
  evidencia_descriptiva: string | null;
  fecha_observacion_local: string | null;
  creado_por_usuario_id: number;
  creado_en_utc: string;
}

export interface ListaSolicitudesInventario {
  items: SolicitudCorreccionInventario[];
  total: number;
  page: number;
  per_page: number;
}

@Injectable({ providedIn: 'root' })
export class InventarioService {
  private url = `${environment.apiUrl}/inventario`;

  constructor(private http: HttpClient) {}

  // ✅ Ahora puede filtrar por sucursal_id (opcional)
obtenerInventario(opts?: { sucursal_id?: number }): Observable<any[]> {
  let params = new HttpParams();
  if (opts?.sucursal_id) params = params.set('sucursal_id', String(opts.sucursal_id));
  return this.http.get<any[]>(`${this.url}/`, { params });
}

  // (opcional) wrapper para mantener compatibilidad donde lo uses así
  obtenerInventarioPorSucursal(sucursal_id: number): Observable<any[]> {
    return this.obtenerInventario({ sucursal_id });
  }

  obtenerInventarioPorId(id: number): Observable<any> {
    return this.http.get<any>(`${this.url}/${id}`);
  }

  crearInventario(data: any): Observable<any> {
    return this.http.post(`${this.url}/`, data);
  }

  editarInventario(id: number, data: any): Observable<any> {
    return this.http.put(`${this.url}/${id}`, data);
  }

  corregirCodigoInterno(
    inventarioId: number,
    data: { codigo_anterior: string; codigo_nuevo: string; motivo: string },
  ): Observable<any> {
    return this.http.post(`${this.url}/${inventarioId}/corregir-codigo`, data);
  }

  obtenerHistorialCodigos(inventarioId: number): Observable<any[]> {
    return this.http.get<any[]>(`${this.url}/${inventarioId}/historial-codigos`);
  }

  eliminarInventario(id: number): Observable<any> {
    return this.http.delete(`${this.url}/${id}`);
  }

  buscarInventario(termino: string): Observable<any[]> {
    return this.http.get<any[]>(
      `${this.url}/buscar?nombre=${encodeURIComponent(termino)}`
    );
  }

  listarSucursales(): Observable<any[]> {
    return this.http.get<any[]>(`${this.url}/sucursales`);
  }

  verExistencias(opts?: { sucursal_id?: number }): Observable<any[]> {
    let params = new HttpParams();
    if (opts?.sucursal_id != null) {
      params = params.set('sucursal_id', String(opts.sucursal_id));
    }
    return this.http.get<any[]>(`${this.url}/existencias`, { params });
  }

  // Piloto V2: lectura por endpoint con autorizacion propia en backend.
  // No sustituye el metodo legacy usado por V1 y el flujo de movimientos.
  verExistenciasV2(opts?: { sucursal_id?: number }): Observable<any[]> {
    let params = new HttpParams();
    if (opts?.sucursal_id != null) {
      params = params.set('sucursal_id', String(opts.sucursal_id));
    }
    return this.http.get<any[]>(`${this.url}/v2/existencias`, { params });
  }

  // E2: almacena y consulta propuestas, nunca aplica cambios al inventario V1.
  crearSolicitudCorreccion(data: SolicitudCorreccionInput): Observable<{
    solicitud: SolicitudCorreccionInventario;
    replayed: boolean;
    possible_pending_duplicate?: boolean;
  }> {
    return this.http.post<{
      solicitud: SolicitudCorreccionInventario;
      replayed: boolean;
      possible_pending_duplicate?: boolean;
    }>(`${this.url}/solicitudes`, data);
  }

  listarSolicitudesCorreccion(params?: {
    sucursal_id?: number; tipo?: TipoSolicitudInventario;
    estado?: 'PENDING' | 'APPROVED' | 'REJECTED'; page?: number; per_page?: number;
  }): Observable<ListaSolicitudesInventario> {
    let httpParams = new HttpParams();
    if (params?.sucursal_id != null) httpParams = httpParams.set('sucursal_id', String(params.sucursal_id));
    if (params?.tipo) httpParams = httpParams.set('tipo', params.tipo);
    if (params?.estado) httpParams = httpParams.set('estado', params.estado);
    if (params?.page != null) httpParams = httpParams.set('page', String(params.page));
    if (params?.per_page != null) httpParams = httpParams.set('per_page', String(params.per_page));
    return this.http.get<ListaSolicitudesInventario>(`${this.url}/solicitudes`, { params: httpParams });
  }

  obtenerSolicitudCorreccion(id: number): Observable<{ solicitud: SolicitudCorreccionInventario }> {
    return this.http.get<{ solicitud: SolicitudCorreccionInventario }>(`${this.url}/solicitudes/${id}`);
  }

  registrarMovimiento(data: any): Observable<any> {
    return this.http.post(`${this.url}/movimientos`, data);
  }

  obtenerMovimientos(): Observable<any[]> {
    return this.http.get<any[]>(`${this.url}/movimientos`);
  }

  importarInventario(file: File): Observable<any> {
    const formData = new FormData();
    formData.append('file', file, file.name);
    return this.http.post(`${this.url}/importar`, formData);
  }

  descargarPlantilla(): Observable<Blob> {
    return this.http.get(`${this.url}/plantilla`, { responseType: 'blob' });
  }

  exportarInventario(): Observable<Blob> {
    return this.http.get(`${this.url}/exportar`, { responseType: 'blob' });
  }

  listarCategoriasInventario(params?: { parent_id?: number; nivel?: number; nombre?: string }): Observable<any[]> {
  let httpParams = new HttpParams();
  if (params?.parent_id != null) httpParams = httpParams.set('parent_id', String(params.parent_id));
  if (params?.nivel != null)     httpParams = httpParams.set('nivel', String(params.nivel));
  if (params?.nombre)            httpParams = httpParams.set('nombre', params.nombre);
  return this.http.get<any[]>(`${this.url}/categorias-inventario`, { params: httpParams });
}

listarInventarioPorCategoriaYSucursal(params: { categoria_inventario_id: number; sucursal_id?: number; }) {
  let httpParams = new HttpParams()
    .set('categoria_inventario_id', String(params.categoria_inventario_id));
  if (params.sucursal_id != null) httpParams = httpParams.set('sucursal_id', String(params.sucursal_id));
  return this.http.get<any[]>(`${this.url}/por-categoria`, { params: httpParams });
}

obtenerEquiposPmPorSucursal(sucursalId: number) {
  const params = new HttpParams().set('sucursal_id', String(sucursalId));
  return this.http.get<any[]>(`${environment.apiUrl}/inventario/equipos`, { params });
}


}

