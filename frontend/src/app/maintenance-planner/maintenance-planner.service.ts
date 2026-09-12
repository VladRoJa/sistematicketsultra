import { Injectable, inject } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { Observable } from 'rxjs';
import { environment } from 'src/environments/environment';

export interface MaintenancePlannerTicket {
  ticket_id: number;
  estado: string;
  planner_status: 'VENCIDO' | 'HOY' | 'PROGRAMADO' | 'SIN_FECHA' | 'FINALIZADO';
  criticidad: number;
  descripcion: string;
  sucursal_id: number | null;
  sucursal: string;
  asignado_a: string | null;
  fecha_creacion: string | null;
  fecha_solucion: string | null;
  fecha_solucion_date: string | null;
  aparato_id: number | null;
  equipo: string;
  codigo_interno: string | null;
  familia: string | null;
  falla: string | null;
  condicion_operativa: string | null;
  necesita_refaccion: boolean;
  descripcion_refaccion: string | null;
}

export interface MaintenancePlannerDay {
  date: string;
  is_today: boolean;
  items: MaintenancePlannerTicket[];
  total: number;
}

export interface MaintenancePlannerBoard {
  module: string;
  version: string;
  window: {
    start_date: string;
    end_date: string;
    today: string;
  };
  metrics: {
    active: number;
    overdue: number;
    today: number;
    week: number;
    unscheduled: number;
    needs_spare_part: number;
  };
  branches: Array<{ id: number; name: string }>;
  days: MaintenancePlannerDay[];
  overdue: MaintenancePlannerTicket[];
  unscheduled: MaintenancePlannerTicket[];
  today_items: MaintenancePlannerTicket[];
  future: MaintenancePlannerTicket[];
  permissions: {
    can_view: boolean;
    can_schedule: boolean;
  };
}

@Injectable({ providedIn: 'root' })
export class MaintenancePlannerService {
  private readonly http = inject(HttpClient);
  private readonly baseUrl = `${environment.apiUrl}/maintenance-planner`;

  getBoard(filters: {
    startDate: string;
    endDate: string;
    branchId?: number | null;
    estado?: string | null;
  }): Observable<MaintenancePlannerBoard> {
    let params = new HttpParams()
      .set('start_date', filters.startDate)
      .set('end_date', filters.endDate);

    if (filters.branchId) {
      params = params.append('branch_id', String(filters.branchId));
    }
    if (filters.estado && filters.estado !== 'todos') {
      params = params.set('estado', filters.estado);
    }

    return this.http.get<MaintenancePlannerBoard>(`${this.baseUrl}/board`, { params });
  }

  scheduleTicket(
    ticketId: number,
    payload: { due_date: string; reason: string }
  ): Observable<{ mensaje: string; ticket: unknown }> {
    return this.http.put<{ mensaje: string; ticket: unknown }>(
      `${this.baseUrl}/tickets/${ticketId}/schedule`,
      payload
    );
  }
}
