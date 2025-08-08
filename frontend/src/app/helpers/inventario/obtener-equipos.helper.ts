//frontend-angular\src\app\helpers\inventario\obtener-equipos.helper.ts

import { HttpClient, HttpHeaders, HttpParams } from '@angular/common/http';
import { environment } from 'src/environments/environment';

export function obtenerEquipos(http: HttpClient, filtros?: { tipo?: string; sucursal_id?: number }) {
  const token = localStorage.getItem('token');
  const headers = new HttpHeaders().set('Authorization', `Bearer ${token}`);
  
  let params = new HttpParams();
  if (filtros?.tipo) params = params.set('tipo', filtros.tipo);
  if (filtros?.sucursal_id) params = params.set('sucursal_id', filtros.sucursal_id.toString());

  return http.get(`${environment.apiUrl}/inventario/equipos`, { headers, params });
}
