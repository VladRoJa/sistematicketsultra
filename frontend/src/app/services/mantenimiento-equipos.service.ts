import { Injectable } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { map, Observable } from 'rxjs';
import { environment } from 'src/environments/environment';
import {
  CompromisoMantenimientoPayload,
  FallaMantenimientoDTO,
  FamiliaEquipoDTO,
  TicketDTO,
} from 'src/app/types/ticket';

export interface RegionReporteMantenimientoDTO {
  id: number;
  nombre: string;
}

export interface DescargaReporteMantenimiento {
  archivo: Blob;
  nombreArchivo: string;
}

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

  obtenerRegionesReporte(): Observable<RegionReporteMantenimientoDTO[]> {
    return this.http.get<RegionReporteMantenimientoDTO[]>(
      `${this.apiUrl}/regiones`,
    );
  }

  descargarReporte(regionId?: number): Observable<DescargaReporteMantenimiento> {
    let params = new HttpParams();
    if (regionId !== undefined) {
      params = params.set('region_id', regionId);
    }

    return this.http.get(`${this.apiUrl}/reporte`, {
      params,
      responseType: 'blob',
      observe: 'response',
    }).pipe(
      map((response) => {
        const contentDisposition = response.headers.get('Content-Disposition');
        const nombreArchivo = this.extraerNombreArchivo(contentDisposition);

        if (!response.body || !nombreArchivo) {
          throw new Error('La respuesta del reporte no incluye un archivo válido.');
        }

        return {
          archivo: response.body,
          nombreArchivo,
        };
      }),
    );
  }

  private extraerNombreArchivo(contentDisposition: string | null): string | null {
    if (!contentDisposition) {
      return null;
    }

    const coincidencia = /filename="?([^";]+)"?/i.exec(contentDisposition);
    return coincidencia?.[1]?.trim() || null;
  }
}
