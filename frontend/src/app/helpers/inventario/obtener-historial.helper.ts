//frontend-angular\src\app\helpers\inventario\obtener-historial.helper.ts

import { HttpClient, HttpHeaders } from '@angular/common/http';
import { environment } from 'src/environments/environment';

export function obtenerHistorialPorEquipo(http: HttpClient, inventario_id: number) {
  const token = localStorage.getItem('token');
  const headers = new HttpHeaders().set('Authorization', `Bearer ${token}`);
  
  return http.get(`${environment.apiUrl}/inventario/${inventario_id}/historial`, { headers });
}
