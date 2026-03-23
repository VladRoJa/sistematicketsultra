// src/app/services/pm-preventivo.service.ts

import { Injectable, inject } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { environment } from 'src/environments/environment';
import { Observable } from 'rxjs';
import {
    DashboardPm,
    PmBitacoraDetalle,
    PmBitacoraResumen,
    PmConfiguracionResumen,
    RegistrarPmPayload,
    SucursalOption,
} from '../models/pm-preventivo.model';

@Injectable({ providedIn: 'root' })
export class PmPreventivoService {
    private http = inject(HttpClient);

    private readonly basePmRoot = `${environment.apiUrl}/pm`;
    private readonly basePm = `${environment.apiUrl}/pm/preventivo`;
    private readonly sucursalesUrl = `${environment.apiUrl}/inventario/sucursales`;

    /** Sucursales permitidas para el usuario autenticado (ya filtradas por backend). */
    getSucursalesPermitidas(): Observable<SucursalOption[]> {
        return this.http.get<SucursalOption[]>(this.sucursalesUrl);
    }

    /** Dashboard PM: atrasados, hoy, próximos. */
    getDashboard(
      sucursalId: number,
      windowDays = 7,
      subcategoria?: string | null
    ): Observable<DashboardPm> {
      let params = new HttpParams()
        .set('sucursal_id', String(sucursalId))
        .set('window_days', String(windowDays));

      if (subcategoria && subcategoria !== 'TODAS') {
        params = params.set('subcategoria', subcategoria);
      }
        return this.http.get<DashboardPm>(`${this.basePm}/dashboard`, { params });
    }

    /** Registrar mantenimiento preventivo (inserta en pm_bitacoras). */
    registrarPreventivo(payload: RegistrarPmPayload): Observable<{ msg: string; id: number }> {
        return this.http.post<{ msg: string; id: number }>(`${this.basePm}/registrar`, payload);
    }

    /** Obtener detalle de una bitácora PM existente. */
    getBitacoraDetalle(bitacoraPmId: number): Observable<PmBitacoraDetalle> {
        return this.http.get<PmBitacoraDetalle>(`${this.basePmRoot}/bitacoras/${bitacoraPmId}`);
    }

    listarBitacoras(
    sucursalId?: number | null,
    fechaDesde?: string | null,
    fechaHasta?: string | null,
    subcategoria?: string | null,
    ): Observable<PmBitacoraResumen[]> {
    let params = new HttpParams();

    if (sucursalId) {
        params = params.set('sucursal_id', String(sucursalId));
    }

    if (fechaDesde) {
        params = params.set('fecha_desde', fechaDesde);
    }

    if (fechaHasta) {
        params = params.set('fecha_hasta', fechaHasta);
    }
    if (subcategoria && subcategoria !== 'TODAS') {
        params = params.set('subcategoria', subcategoria);
    }

    return this.http.get<PmBitacoraResumen[]>(`${this.basePmRoot}/bitacoras`, { params });
}

    listarConfiguracionesPm(
    sucursalId?: number | null,
    ): Observable<PmConfiguracionResumen[]> {
    let params = new HttpParams();

    if (sucursalId) {
        params = params.set('sucursal_id', String(sucursalId));
    }

    return this.http.get<PmConfiguracionResumen[]>(`${this.basePmRoot}/configuraciones`, { params });
}

getCalendarioPm(
  anio: number,
  mes: number,
  sucursalesIds?: number[] | null,
  semanaAnio?: number | null,
  subcategoria?: string | null
): Observable<any> {
  let params = new HttpParams()
    .set('anio', String(anio))
    .set('mes', String(mes));

  if (sucursalesIds && sucursalesIds.length > 0) {
    for (const sucursalId of sucursalesIds) {
      if (sucursalId !== -1) {
        params = params.append('sucursales_ids', String(sucursalId));
      }
    }
  }

  if (semanaAnio) {
    params = params.set('semana_anio', String(semanaAnio));
  }

  if (subcategoria && subcategoria !== 'TODAS') {
    params = params.set('subcategoria', subcategoria);
  }
  return this.http.get<any>(`${this.basePmRoot}/calendario`, { params });
}


    crearConfiguracionPm(payload: {
    inventario_id: number;
    sucursal_id: number;
    frecuencia_dias: number;
    semana_programada_mes?: number;
    dia_programado_semana?: number;
    fecha_base_programacion: string;
    activo: boolean;
    }): Observable<PmConfiguracionResumen> {
    return this.http.post<PmConfiguracionResumen>(`${this.basePmRoot}/configuraciones`, payload);
}

actualizarConfiguracionPm(
  configId: number,
  payload: {
    frecuencia_dias?: number;
    semana_programada_mes?: number;
    dia_programado_semana?: number;
    fecha_base_programacion?: string;
    activo?: boolean;
  }
): Observable<PmConfiguracionResumen> {
  return this.http.put<PmConfiguracionResumen>(
    `${this.basePmRoot}/configuraciones/${configId}`,
    payload
  );
}

crearValidacionPm(payload: {
    bitacora_pm_id: number;
    decision: 'VALIDADO' | 'RECHAZADO';
    motivo?: string;
}): Observable<{ msg: string; id: number; bitacora_pm_id: number; decision: string }> {
    return this.http.post<{ msg: string; id: number; bitacora_pm_id: number; decision: string }>(
        `${this.basePmRoot}/validaciones`,
        payload
    );
}
}