// frontend/src/app/pm/services/pm-inventario.service.ts


import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';

import { obtenerEquipos } from '../../../helpers/inventario/obtener-equipos.helper';

export interface PmEquipoItem {
  inventario_id: number;
  sucursal_id: number;
  nombre?: string;
  marca?: string;
  modelo?: string;
  codigo_interno?: string;
  tipo?: string;
  [key: string]: any;
}

@Injectable({ providedIn: 'root' })
export class PmInventarioService {
  constructor(private http: HttpClient) {}

  listarEquipos(filtros?: { tipo?: string; sucursal_id?: number }): Observable<PmEquipoItem[]> {
    return obtenerEquipos(this.http, filtros) as Observable<PmEquipoItem[]>;
  }
}