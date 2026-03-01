// frontend\src\app\services\admin-usuarios.service.ts

import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';

export interface AdminUsuarioSucursalesResponse {
  user_id: number;
  sucursales_ids: number[];
}

export interface AdminUsuarioSucursalesUpdateRequest {
  sucursales_ids: number[];
}

export interface AdminUsuarioSucursalesUpdateResponse {
  mensaje: string;
  user_id: number;
  sucursales_ids: number[];
}

@Injectable({ providedIn: 'root' })
export class AdminUsuariosService {
  private readonly baseUrl = '/api';

  constructor(private http: HttpClient) {}

  getSucursalesDeUsuario(userId: number): Observable<AdminUsuarioSucursalesResponse> {
    return this.http.get<AdminUsuarioSucursalesResponse>(
      `${this.baseUrl}/admin/usuarios/${userId}/sucursales`
    );
  }

  actualizarSucursalesDeUsuario(
    userId: number,
    payload: AdminUsuarioSucursalesUpdateRequest
  ): Observable<AdminUsuarioSucursalesUpdateResponse> {
    return this.http.put<AdminUsuarioSucursalesUpdateResponse>(
      `${this.baseUrl}/admin/usuarios/${userId}/sucursales`,
      payload
    );
  }
}