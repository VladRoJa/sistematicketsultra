// frontend/src/app/pm/services/pm-inventario.service.ts


import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';
import { map } from 'rxjs/operators';

import { obtenerEquipos } from '../../../helpers/inventario/obtener-equipos.helper';

export interface PmEquipoItem {
  inventario_id: number;
  sucursal_id: number;
  id?: number; // para autocompletar, es el mismo que inventario_id pero como id
  nombre?: string;
  marca?: string;
  modelo?: string;
  codigo_interno?: string;
  tipo?: string;
  [key: string]: any;
  categoria?: string; // para compatibilidad con respuesta del backend
}

@Injectable({ providedIn: 'root' })
export class PmInventarioService {
  constructor(private http: HttpClient) {}

  listarEquipos(filtros?: { tipo?: string; sucursal_id?: number }): Observable<PmEquipoItem[]> {
    return obtenerEquipos(this.http, filtros) as Observable<PmEquipoItem[]>;
  }

  listarEquiposOperativosSucursal(sucursalId: number): Observable<PmEquipoItem[]> {
  return obtenerEquipos(this.http, {
    sucursal_id: sucursalId,
  }) as Observable<PmEquipoItem[]>;
}

listarEquiposPreventivosOperativos(
  sucursalId: number,
  windowDays: number,
  ventanaModo: 'ATRASADOS' | 'HOY' | 'PROXIMOS_7' | 'PROXIMOS_14'
): Observable<PmEquipoItem[]> {

  return this.http.get<any>(`/api/pm/preventivo/dashboard`, {
    params: {
      sucursal_id: String(sucursalId),
      window_days: String(windowDays),
    },
  }).pipe(
    map((data) => {
        const atrasados = Array.isArray(data?.atrasados) ? data.atrasados : [];
        const hoy = Array.isArray(data?.hoy) ? data.hoy : [];
        const proximos = Array.isArray(data?.proximos) ? data.proximos : [];

        let combinados: any[] = [];

        if (ventanaModo === 'ATRASADOS') {
          combinados = atrasados;
        } else if (ventanaModo === 'HOY') {
          combinados = hoy;
        } else {
          combinados = proximos;
        }

      const vistos = new Set<number>();
      const resultado: PmEquipoItem[] = [];

      for (const item of combinados) {
        const inventarioId = Number(item?.inventario_id);
        if (!inventarioId || vistos.has(inventarioId)) {
          continue;
        }

        vistos.add(inventarioId);
        resultado.push({
          inventario_id: inventarioId,
          id: inventarioId,
          sucursal_id: Number(item?.sucursal_id),
          nombre: item?.nombre,
          marca: item?.marca,
          codigo_interno: item?.codigo_interno,
          tipo: item?.tipo,
          categoria: item?.categoria,
          estado_pm: item?.estado,
          proxima_fecha: item?.proxima_fecha,
          dias_restantes: item?.dias_restantes,
        });
      }

      return resultado;
    })
  );
}

}