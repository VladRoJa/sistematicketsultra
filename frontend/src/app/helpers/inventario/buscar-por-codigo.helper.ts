//frontend-angular\src\app\helpers\inventario\buscar-por-codigo.helper.ts

import { HttpClient, HttpHeaders, HttpParams } from '@angular/common/http';
import { environment } from 'src/environments/environment';

export function buscarEquipoPorCodigo(http: HttpClient, codigo: string) {
  const token = localStorage.getItem('token');
  const headers = new HttpHeaders().set('Authorization', `Bearer ${token}`);
  const params = new HttpParams().set('codigo', codigo.toUpperCase());

  return http.get(`${environment.apiUrl}/inventario/buscar-por-codigo`, { headers, params });
}
