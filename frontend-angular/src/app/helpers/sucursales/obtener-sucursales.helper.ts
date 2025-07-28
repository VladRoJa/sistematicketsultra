//frontend-angular\src\app\helpers\inventario\obtener-sucursales.helper.ts

import { HttpClient, HttpHeaders } from '@angular/common/http';
import { environment } from 'src/environments/environment';

export function obtenerSucursales(http: HttpClient) {
  const token = localStorage.getItem('token');
  const headers = new HttpHeaders().set('Authorization', `Bearer ${token}`);

  return http.get(`${environment.apiUrl}/sucursales/listar`, { headers });
}
