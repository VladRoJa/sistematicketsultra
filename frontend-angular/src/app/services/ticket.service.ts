//ticket.service.ts

import { Injectable } from '@angular/core';
import { HttpClient, HttpHeaders, HttpParams } from '@angular/common/http';
import { Observable } from 'rxjs';

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
}
