//usuario.service.ts

import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';
import { environment } from 'src/environments/environment';

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
}
