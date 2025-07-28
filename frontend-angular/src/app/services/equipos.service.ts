// src/app/services/equipos.service.ts
import { Injectable } from '@angular/core';
import { HttpClient, HttpHeaders, HttpParams } from '@angular/common/http';
import { environment } from 'src/environments/environment';

@Injectable({ providedIn: 'root' })
export class EquiposService {
  private apiUrl = `${environment.apiUrl}/inventario/equipos`;

  constructor(private http: HttpClient) {}

  // ✅ Acepta un solo objeto de parámetros, con valores opcionales
  obtenerEquipos(params: { sucursal_id?: number; tipo?: string } = {}) {
    const token = localStorage.getItem('token');
    const headers = token ? new HttpHeaders().set('Authorization', `Bearer ${token}`) : new HttpHeaders();

    // 👇 Convierte params a HttpParams
    let httpParams = new HttpParams();
    Object.keys(params).forEach(key => {
      if (params[key] !== undefined && params[key] !== null) {
        httpParams = httpParams.set(key, params[key]);
      }
    });

    return this.http.get<any[]>(this.apiUrl, { headers, params: httpParams });
  }
}
