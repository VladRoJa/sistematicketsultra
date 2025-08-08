//

import { HttpClient, HttpHeaders } from '@angular/common/http';
import { environment } from 'src/environments/environment';

export function obtenerExistencias(http: HttpClient) {
  const token = localStorage.getItem('token');
  const headers = new HttpHeaders().set('Authorization', `Bearer ${token}`);

  return http.get(`${environment.apiUrl}/inventario/existencias`, { headers });
}
