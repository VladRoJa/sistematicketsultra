import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';
import { environment } from 'src/environments/environment';
import {
  CompromisoMantenimientoPayload,
  FallaMantenimientoDTO,
  FamiliaEquipoDTO,
  TicketDTO,
} from 'src/app/types/ticket';

@Injectable({ providedIn: 'root' })
export class MantenimientoEquiposService {
  private readonly apiUrl = `${environment.apiUrl}/mantenimiento-equipos`;

  constructor(private readonly http: HttpClient) {}

  obtenerFamilias(): Observable<FamiliaEquipoDTO[]> {
    return this.http.get<FamiliaEquipoDTO[]>(`${this.apiUrl}/familias`);
  }

  obtenerFallas(familiaEquipoId: number): Observable<FallaMantenimientoDTO[]> {
    return this.http.get<FallaMantenimientoDTO[]>(
      `${this.apiUrl}/familias/${familiaEquipoId}/fallas`,
    );
  }

  guardarCompromiso(
    ticketId: number,
    payload: CompromisoMantenimientoPayload,
  ): Observable<{
    mensaje: string;
    ticket: TicketDTO;
    notificados: string[];
  }> {
    return this.http.put<{
      mensaje: string;
      ticket: TicketDTO;
      notificados: string[];
    }>(
      `${this.apiUrl}/tickets/${ticketId}/compromiso`,
      payload,
    );
  }

  descargarReporte(): Observable<Blob> {
    return this.http.get(`${this.apiUrl}/reporte`, { responseType: 'blob' });
  }
}
