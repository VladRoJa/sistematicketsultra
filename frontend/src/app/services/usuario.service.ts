//usuario.service.ts

import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
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

export interface SucursalUsuarioOption {
  sucursal_id: number;
  sucursal: string;
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

  getSucursales(): Observable<SucursalUsuarioOption[]> {
    return this.http.get<SucursalUsuarioOption[]>(
      `${environment.apiUrl}/sucursales/listar`
    );
  }

  getDepartamentos(): Observable<DepartamentosUsuarioResponse> {
    return this.http.get<DepartamentosUsuarioResponse>(
      `${environment.apiUrl}/departamentos/listar`
    );
  }

}
