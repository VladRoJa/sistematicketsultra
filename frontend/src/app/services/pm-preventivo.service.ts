// src/app/services/pm-preventivo.service.ts

import { Injectable, inject } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { Observable } from 'rxjs';
import {
    DashboardPm,
    RegistrarPmPayload,
    SucursalOption,
} from '../models/pm-preventivo.model';

@Injectable({ providedIn: 'root' })
export class PmPreventivoService {
    private http = inject(HttpClient);

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
}
