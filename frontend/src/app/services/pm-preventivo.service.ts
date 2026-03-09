// src/app/services/pm-preventivo.service.ts

import { Injectable, inject } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
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

    private readonly basePmRoot = '/api/pm';
    private readonly basePm = '/api/pm/preventivo';
    private readonly sucursalesUrl = '/api/inventario/sucursales';

    /** Sucursales permitidas para el usuario autenticado (ya filtradas por backend). */
    getSucursalesPermitidas(): Observable<SucursalOption[]> {
        return this.http.get<SucursalOption[]>(this.sucursalesUrl);
    }

    /** Dashboard PM: atrasados, hoy, próximos. */
    getDashboard(sucursalId: number, windowDays = 7): Observable<DashboardPm> {
        const params = new HttpParams()
            .set('sucursal_id', String(sucursalId))
            .set('window_days', String(windowDays));

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

    crearConfiguracionPm(payload: {
    inventario_id: number;
    sucursal_id: number;
    frecuencia_dias: number;
    activo: boolean;
    }): Observable<PmConfiguracionResumen> {
    return this.http.post<PmConfiguracionResumen>(`${this.basePmRoot}/configuraciones`, payload);
}

    actualizarConfiguracionPm(
    configId: number,
    payload: {
        frecuencia_dias?: number;
        activo?: boolean;
    }
    ): Observable<PmConfiguracionResumen> {
    return this.http.put<PmConfiguracionResumen>(
        `${this.basePmRoot}/configuraciones/${configId}`,
        payload
    );
}
}