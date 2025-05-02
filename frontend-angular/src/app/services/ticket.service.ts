//ticket.service.ts

import { Injectable } from '@angular/core';
import { HttpClient, HttpHeaders, HttpParams } from '@angular/common/http';
import { Observable } from 'rxjs';


export interface TicketsResponse {
  mensaje: string;
  tickets: any[];
  total_tickets: number;
}

@Injectable({
  providedIn: 'root'
})
export class TicketService {
  // Base URL del backend para la gestión de tickets.
  // Se asume que la ruta para obtener tickets es '/api/tickets/all'
  private apiUrl = 'http://localhost:5000/api/tickets';

  constructor(private http: HttpClient) {}

  /**
   * Obtiene la lista de tickets con soporte para paginación.
   *
   * La lógica de filtrado (por sucursal, departamento o todos)
   * se aplica en el backend según el usuario autenticado.
   *
   * @param limit Número máximo de tickets a retornar por página (por defecto 15).
   * @param offset Número de tickets a saltar para paginación (por defecto 0).
   * @returns Observable que emite la respuesta del backend, incluyendo la lista de tickets y el total.
        * Obtiene tickets aplicando filtros y pudiendo omitir paginación.
   * @param filters Objeto con las posibles propiedades de filtro:
   *   - estado?: string
   *   - departamento_id?: string | number
   *   - criticidad?: string | number
   *   - no_paging?: boolean
   *   - limit?: number
   *   - offset?: number
  */

    

  getTickets(limit: number = 15, offset: number = 0): Observable<any> {
    // Obtener el token desde localStorage para la autorización.
    const token = localStorage.getItem('token');
    if (!token) {
      console.error("❌ No hay token en localStorage.");
      // Se podría retornar throwError() o un Observable vacío en función del manejo de errores.
      return new Observable();
    }

    // Configuración de headers, incluyendo el token en la cabecera Authorization.
    const headers = new HttpHeaders()
      .set('Authorization', `Bearer ${token}`)
      .set('Content-Type', 'application/json');

    // Configuración de los parámetros de paginación.
    const params = new HttpParams()
      .set('limit', limit.toString())
      .set('offset', offset.toString());

    // Se hace la petición GET a la ruta '/all' del backend.
    // withCredentials: true se utiliza si el backend requiere el envío de cookies.
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

    // Filtros
    if (filters.estado) {
      params = params.set('estado', filters.estado);
    }
    if (filters.departamento_id !== undefined) {
      params = params.set('departamento_id', String(filters.departamento_id));
    }
    if (filters.criticidad !== undefined) {
      params = params.set('criticidad', String(filters.criticidad));
    }

    // Omitir paginación
    if (filters.no_paging) {
      params = params.set('no_paging', 'true');
    } else {
      // Paginación normal
      const limit = filters.limit ?? 15;
      const offset = filters.offset ?? 0;
      params = params.set('limit', limit.toString());
      params = params.set('offset', offset.toString());
    }

    // Llamada al nuevo endpoint /list
    return this.http.get<TicketsResponse>(`${this.apiUrl}/tickets/list`, { params });
  }


  getAllTicketsFiltered(filtros: any): Observable<TicketsResponse> {
    // Iniciamos los parámetros HTTP vacíos
    let params: HttpParams = new HttpParams();

    // Solo se añaden parámetros si existen valores en el objeto filtros.
    // Si filtros está vacío, la query se construirá sin restricciones (y devolverá todos los registros).
    if (filtros.estado) {
      params = params.set('estado', filtros.estado);
    }
    if (filtros.departamento_id) {
      params = params.set('departamento_id', filtros.departamento_id);
    }
    if (filtros.criticidad) {
      params = params.set('criticidad', filtros.criticidad);
    }
    if (filtros.username) {
      params = params.set('username', filtros.username);
    }
    if (filtros.fechaDesde) {
      params = params.set('fecha_desde', filtros.fechaDesde); // Ejemplo: '2025-02-22'
    }
    if (filtros.fechaHasta) {
      params = params.set('fecha_hasta', filtros.fechaHasta); // Ejemplo: '2025-03-22'
    }
    if (filtros.fechaFinDesde) {
      params = params.set('fecha_fin_desde', filtros.fechaFinDesde);
    }
    if (filtros.fechaFinHasta) {
      params = params.set('fecha_fin_hasta', filtros.fechaFinHasta);
    }

    // Se fuerza que la paginación se omita, para obtener la data completa
    params = params.set('no_paging', 'true');

    // Realiza la petición GET a la ruta /list del backend
    return this.http.get<TicketsResponse>(`${this.apiUrl}/list`, { params });
  }

  exportarTickets(filtros: any): Observable<Blob> {
    const token = localStorage.getItem('token');
    if (!token) {
      console.error("❌ No hay token para exportar.");
      return new Observable<Blob>();
    }
  
    console.log("📤 Filtros enviados al backend:", filtros); // Agrega esto temporalmente
  
    let params = new HttpParams();
    for (const clave in filtros) {
      const valor = filtros[clave];
      if (Array.isArray(valor)) {
        valor.forEach((v: string) => {
          params = params.append(clave, v);
        });
      } else if (valor !== undefined) {
        params = params.set(clave, valor);
      }
    }
  
    const headers = new HttpHeaders().set('Authorization', `Bearer ${token}`);
    return this.http.get('http://localhost:5000/api/tickets/export-excel', {
      headers,
      params,
      responseType: 'blob'
    });
  }
  
  
  
}
