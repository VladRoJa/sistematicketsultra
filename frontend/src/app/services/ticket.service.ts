// frontend/src/app/services/ticket.service.ts
import { Injectable } from '@angular/core';
import { HttpClient, HttpHeaders, HttpParams } from '@angular/common/http';
import { Observable, throwError } from 'rxjs';
import { environment } from 'src/environments/environment';
import { TicketDTO, SetCompromisoPayload, CierreRechazoPayload } from 'src/app/types/ticket';

export interface TicketsResponse {
  mensaje: string;
  tickets: any[];
  total_tickets: number;
}

@Injectable({ providedIn: 'root' })
export class TicketService {
  private apiUrl = `${environment.apiUrl}/tickets`;

  constructor(private http: HttpClient) {}

  /** Headers JSON con Authorization si hay token */
  private authJsonHeaders(): HttpHeaders {
    const token = localStorage.getItem('token');
    let headers = new HttpHeaders().set('Content-Type', 'application/json');
    return token ? headers.set('Authorization', `Bearer ${token}`) : headers;
  }

  // ─────────────────────────────────────────────
  // LISTADOS
  // ─────────────────────────────────────────────
  getTickets(limit: number = 15, offset: number = 0): Observable<any> {
    const token = localStorage.getItem('token');
    if (!token) return throwError(() => new Error('NO_TOKEN'));
    const headers = this.authJsonHeaders();
    const params = new HttpParams().set('limit', limit).set('offset', offset);
    return this.http.get<any>(`${this.apiUrl}/all`, { headers, params, withCredentials: true });
  }

  getTicketsConFiltros(filters: {
    estado?: string;
    departamento_id?: number;
    criticidad?: number;
    no_paging?: boolean;
    limit?: number;
    offset?: number;
  }): Observable<TicketsResponse> {
    let params = new HttpParams();

    if (filters.estado) params = params.set('estado', filters.estado);
    if (filters.departamento_id !== undefined) params = params.set('departamento_id', String(filters.departamento_id));
    if (filters.criticidad !== undefined) params = params.set('criticidad', String(filters.criticidad));

    if (filters.no_paging) {
      params = params.set('no_paging', 'true');
    } else {
      params = params.set('limit', String(filters.limit ?? 15))
                     .set('offset', String(filters.offset ?? 0));
    }

    const headers = this.authJsonHeaders();
    return this.http.get<TicketsResponse>(`${this.apiUrl}/list`, { headers, params, withCredentials: true });
  }

  getAllTicketsFiltered(filtros: any): Observable<TicketsResponse> {
    let params = new HttpParams();

    if (filtros.estado) params = params.set('estado', filtros.estado);
    if (filtros.departamento_id) params = params.set('departamento_id', filtros.departamento_id);
    if (filtros.criticidad) params = params.set('criticidad', filtros.criticidad);
    if (filtros.username) params = params.set('username', filtros.username);
    if (filtros.fechaDesde) params = params.set('fecha_desde', filtros.fechaDesde);
    if (filtros.fechaHasta) params = params.set('fecha_hasta', filtros.fechaHasta);
    if (filtros.fechaFinDesde) params = params.set('fecha_fin_desde', filtros.fechaFinDesde);
    if (filtros.fechaFinHasta) params = params.set('fecha_fin_hasta', filtros.fechaFinHasta);

    params = params.set('no_paging', 'true');

    const headers = this.authJsonHeaders();
    return this.http.get<TicketsResponse>(`${this.apiUrl}/list`, { headers, params, withCredentials: true });
  }

  exportarTickets(filtros: any): Observable<Blob> {
    const token = localStorage.getItem('token');
    if (!token) return throwError(() => new Error('NO_TOKEN'));

    let params = new HttpParams();
    for (const k in filtros) {
      const v = filtros[k];
      if (Array.isArray(v)) v.forEach((x: string) => (params = params.append(k, x)));
      else if (v !== undefined) params = params.set(k, v);
    }

    const headers = new HttpHeaders().set('Authorization', `Bearer ${token}`);
    return this.http.get(`${this.apiUrl}/export-excel`, { headers, params, responseType: 'blob' });
  }

  // ─────────────────────────────────────────────
  // UPDATES / ACCIONES
  // ─────────────────────────────────────────────

  /** Actualiza (PUT) usando la ruta real /update/:id */
  updateTicket(id: number, payload: Partial<TicketDTO>): Observable<any> {
    const token = localStorage.getItem('token');
    if (!token) return throwError(() => new Error('NO_TOKEN'));
    const headers = this.authJsonHeaders();
    return this.http.put<any>(`${this.apiUrl}/update/${id}`, payload, { headers, withCredentials: true });
  }

  /**
   * Fija/actualiza fecha de compromiso y (si aplica) refacción.
   * Ruta backend real: PUT /compromiso/:id
   */
  setCompromiso(id: number, payload: SetCompromisoPayload): Observable<any> {
    const token = localStorage.getItem('token');
    if (!token) return throwError(() => new Error('NO_TOKEN'));
    const headers = this.authJsonHeaders();
    return this.http.put<any>(`${this.apiUrl}/compromiso/${id}`, payload, { headers, withCredentials: true });
  }

  // ── RRHH (pre-aprobación) ───────────────────
  rrhhSolicitar(id: number, aprobadorUsername?: string): Observable<any> {
    const token = localStorage.getItem('token');
    if (!token) return throwError(() => new Error('NO_TOKEN'));
    const headers = this.authJsonHeaders();
    const body = aprobadorUsername ? { aprobador_username: aprobadorUsername } : {};
    return this.http.post<any>(`${this.apiUrl}/rrhh/solicitar/${id}`, body, { headers, withCredentials: true });
  }

  rrhhAprobar(id: number, comentario?: string): Observable<any> {
    const token = localStorage.getItem('token');
    if (!token) return throwError(() => new Error('NO_TOKEN'));
    const headers = this.authJsonHeaders();
    const body = comentario ? { comentario } : {};
    return this.http.post<any>(`${this.apiUrl}/rrhh/aprobar/${id}`, body, { headers, withCredentials: true });
  }

  rrhhRechazar(id: number, comentario?: string): Observable<any> {
    const token = localStorage.getItem('token');
    if (!token) return throwError(() => new Error('NO_TOKEN'));
    const headers = this.authJsonHeaders();
    const body = comentario ? { comentario } : {};
    return this.http.post<any>(`${this.apiUrl}/rrhh/rechazar/${id}`, body, { headers, withCredentials: true });
  }

  // ── Doble check de cierre ───────────────────
  cierreSolicitar(
    id: number,
    payload: { costo_solucion: number | null; notas_cierre: string | null }
  ): Observable<any> {
    const token = localStorage.getItem('token');
    if (!token) return throwError(() => new Error('NO_TOKEN'));

    const headers = this.authJsonHeaders();

    return this.http.post<any>(
      `${this.apiUrl}/cierre/solicitar/${id}`,
      payload,
      { headers, withCredentials: true }
    );
  }


  cierreAprobarJefe(id: number): Observable<any> {
    const token = localStorage.getItem('token');
    if (!token) return throwError(() => new Error('NO_TOKEN'));
    const headers = this.authJsonHeaders();
    return this.http.post<any>(`${this.apiUrl}/cierre/aprobar-jefe/${id}`, {}, { headers, withCredentials: true });
  }

  cierreRechazarJefe(id: number, payload: CierreRechazoPayload): Observable<any> {
    const token = localStorage.getItem('token');
    if (!token) return throwError(() => new Error('NO_TOKEN'));
    if (!payload?.motivo || !payload?.nueva_fecha_solucion) {
      return throwError(() => new Error('Falta motivo o nueva_fecha_solucion'));
    }
    const headers = this.authJsonHeaders();
    return this.http.post<any>(`${this.apiUrl}/cierre/rechazar-jefe/${id}`, payload, { headers, withCredentials: true });
  }

  cierreAceptarCreador(id: number): Observable<any> {
    const token = localStorage.getItem('token');
    if (!token) return throwError(() => new Error('NO_TOKEN'));
    const headers = this.authJsonHeaders();
    return this.http.post<any>(`${this.apiUrl}/cierre/aceptar-creador/${id}`, {}, { headers, withCredentials: true });
  }

  cierreRechazarCreador(id: number, payload: CierreRechazoPayload): Observable<any> {
    const token = localStorage.getItem('token');
    if (!token) return throwError(() => new Error('NO_TOKEN'));
    if (!payload?.motivo || !payload?.nueva_fecha_solucion) {
      return throwError(() => new Error('Falta motivo o nueva_fecha_solucion'));
    }
    const headers = this.authJsonHeaders();
    return this.http.post<any>(`${this.apiUrl}/cierre/rechazar-creador/${id}`, payload, { headers, withCredentials: true });
  }

  // ── Notificaciones ──────────────────────────
  notifyTicket(
    id: number,
    payload: { emails?: string[]; channels?: string[]; mensaje?: string }
  ): Observable<any> {
    const token = localStorage.getItem('token');
    if (!token) return throwError(() => new Error('NO_TOKEN'));
    const headers = this.authJsonHeaders();
    return this.http.post<any>(`${this.apiUrl}/notify/${id}`, payload || {}, { headers, withCredentials: true });
  }
}
