//permiso.service.ts

import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';

@Injectable({
  providedIn: 'root'
})
export class PermisoService {
  private apiUrl = 'http://localhost:5000/api/permisos';

  constructor(private http: HttpClient) { }

  // Método para obtener los permisos de un usuario específico
  getPermisosUsuario(userId: number): Observable<any> {
    return this.http.get<any>(`${this.apiUrl}/listar/${userId}`);
  }
}
