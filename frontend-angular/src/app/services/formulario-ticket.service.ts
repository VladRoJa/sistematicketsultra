// src/app/services/formulario-ticket.service.ts

import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { environment } from 'src/environments/environment';
import { Observable } from 'rxjs';

@Injectable({ providedIn: 'root' })
export class FormularioTicketService {
  private apiUrl = `${environment.apiUrl}/formulario_ticket`;

  constructor(private http: HttpClient) {}

  getFormularios(departamentoId?: number): Observable<any[]> {
    let url = `${this.apiUrl}/lista`;
    if (departamentoId) {
      url += `?departamento_id=${departamentoId}`;
    }
    return this.http.get<any[]>(url);
  }

  getFormularioPorId(id: number): Observable<any> {
    return this.http.get<any>(`${this.apiUrl}/${id}`);
  }
}
