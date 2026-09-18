//usuario.service.ts

import { Injectable } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { Observable } from 'rxjs';
import { environment } from 'src/environments/environment';

export interface CrearUsuarioRequest {
  username: string;
  password: string;
  rol: string;
  sucursal_id: number;
  department_id: number;
  email?: string | null;
}

export interface CrearUsuarioResponse {
  msg: string;
  id: number;
}

export interface UsuarioAdminOption {
  id: number;
  username: string;
  rol: string;
  sucursal_id: number | null;
  department_id: number | null;
  email?: string | null;
}

export interface CambiarPasswordUsuarioRequest {
  password: string;
}

export interface UsuarioMutationResponse {
  msg: string;
}

export interface SucursalUsuarioOption {
  sucursal_id: number;
  sucursal: string;
  is_demo?: boolean;
}

export interface DepartamentoUsuarioOption {
  id: number;
  nombre: string;
}

export interface DepartamentosUsuarioResponse {
  departamentos: DepartamentoUsuarioOption[];
}

@Injectable({
  providedIn: 'root'
})
export class UsuarioService {
  // Asegúrate de que la URL corresponda a tu endpoint real.
  private apiUrl = `${environment.apiUrl}/usuarios`;

  constructor(private http: HttpClient) { }

  // Método para obtener la lista de usuarios.
  getUsuarios(): Observable<any> {
    return this.http.get<any>(`${this.apiUrl}/listar`);
  }
  crearUsuario(payload: CrearUsuarioRequest): Observable<CrearUsuarioResponse> {
    return this.http.post<CrearUsuarioResponse>(this.apiUrl, payload);
  }

  listarUsuariosAdmin(): Observable<UsuarioAdminOption[]> {
    return this.http.get<UsuarioAdminOption[]>(this.apiUrl);
  }

  cambiarPasswordUsuario(
    userId: number,
    payload: CambiarPasswordUsuarioRequest,
  ): Observable<UsuarioMutationResponse> {
    return this.http.put<UsuarioMutationResponse>(
      `${this.apiUrl}/${userId}`,
      payload,
    );
  }

  getSucursales(): Observable<SucursalUsuarioOption[]> {
    const params = new HttpParams().set('audience', 'operational');
    return this.http.get<SucursalUsuarioOption[]>(
      `${environment.apiUrl}/sucursales/listar`,
      { params }
    );
  }

  getDepartamentos(): Observable<DepartamentosUsuarioResponse> {
    return this.http.get<DepartamentosUsuarioResponse>(
      `${environment.apiUrl}/departamentos/listar`
    );
  }

}
