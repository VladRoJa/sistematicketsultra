//frontend\src\app\helpers\inventario\obtener-sucursales.helper.ts

import { HttpClient, HttpHeaders, HttpParams } from '@angular/common/http';
import { environment } from 'src/environments/environment';

export function obtenerSucursales(http: HttpClient) {
  const token = localStorage.getItem('token');
  const headers = new HttpHeaders().set('Authorization', `Bearer ${token}`);
  const params = new HttpParams().set('audience', 'operational');

  return http.get(`${environment.apiUrl}/sucursales/listar`, { headers, params });
}
