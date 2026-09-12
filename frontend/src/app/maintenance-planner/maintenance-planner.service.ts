import { Injectable, inject } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { Observable, switchMap } from 'rxjs';
import { environment } from 'src/environments/environment';
import { SessionService } from '../core/auth/session.service';
import { TicketService } from '../services/ticket.service';

export type MaintenancePlannerAudience = 'operational' | 'analytical';

export interface MaintenancePlannerHistoryItem {
  fecha?: string | null;
  fecha_solucion?: string | null;
  fechaCambio?: string | null;
  fecha_cambio?: string | null;
  cambiadoPor?: string | null;
  usuario?: string | null;
  username?: string | null;
  motivo?: string | null;
  comentario?: string | null;
  razon?: string | null;
  tipo?: string | null;
  evento?: string | null;
  origen?: string | null;
  [key: string]: unknown;
}

export interface MaintenancePlannerTicket {
  ticket_id: number;
  estado: string;
  planner_status: 'VENCIDO' | 'HOY' | 'PROGRAMADO' | 'SIN_FECHA' | 'FINALIZADO';
  criticidad: number;
  descripcion: string;
  username: string;
  sucursal_id: number | null;
  sucursal: string;
  sucursal_is_demo: boolean;
  asignado_a: string | null;
  fecha_creacion: string | null;
  fecha_en_progreso: string | null;
  fecha_finalizado: string | null;
  fecha_solucion: string | null;
  fecha_solucion_date: string | null;
  historial_fechas: MaintenancePlannerHistoryItem[];
  aparato_id: number | null;
  equipo: string;
  codigo_interno: string | null;
  familia: string | null;
  falla: string | null;
  problema_detectado: string | null;
  condicion_operativa: string | null;
  ubicacion: string | null;
  categoria: string | null;
  subcategoria: string | null;
  detalle: string | null;
  necesita_refaccion: boolean;
  descripcion_refaccion: string | null;
  refaccion_definida_por_jefe: boolean;
  estado_cierre: string | null;
  motivo_rechazo_cierre: string | null;
  costo_solucion: number | null;
  notas_cierre: string | null;
  url_evidencia: string | null;
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
  audience: MaintenancePlannerAudience;
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
  branches: Array<{ id: number; name: string; is_demo: boolean }>;
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
  private readonly ticketService = inject(TicketService);
  private readonly session = inject(SessionService);
  private readonly baseUrl = `${environment.apiUrl}/maintenance-planner`;

  getBoard(filters: {
    startDate: string;
    endDate: string;
    branchId?: number | null;
    estado?: string | null;
    audience?: MaintenancePlannerAudience;
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
    if (filters.audience) {
      params = params.set('audience', filters.audience);
    }

    return this.http.get<MaintenancePlannerBoard>(`${this.baseUrl}/board`, { params });
  }

  /**
   * Compatibilidad con el endpoint propio del Planner.
   * La UI V2 ya no lo usa para editar compromisos; conserva la ruta para
   * integraciones existentes mientras el módulo migra al contrato común de Tickets.
   */
  scheduleTicket(
    ticketId: number,
    payload: { due_date: string; reason: string }
  ): Observable<{ mensaje: string; ticket: unknown }> {
    return this.http.put<{ mensaje: string; ticket: unknown }>(
      `${this.baseUrl}/tickets/${ticketId}/schedule`,
      payload
    );
  }

  updateCommitment(
    ticket: MaintenancePlannerTicket,
    dueDate: string,
    reason: string,
  ): Observable<unknown> {
    const trimmedReason = reason.trim();
    if (!dueDate || !trimmedReason) {
      throw new Error('La fecha y el motivo son obligatorios.');
    }

    const dueDateIso = this.toCommitmentIso(dueDate);
    const nowIso = new Date().toISOString();
    const history = Array.isArray(ticket.historial_fechas)
      ? ticket.historial_fechas.map((item) => ({ ...item }))
      : [];

    history.push({
      fecha: dueDateIso,
      cambiadoPor: String(this.session.getUser()?.username || '').trim(),
      fechaCambio: nowIso,
      motivo: trimmedReason,
      origen: 'maintenance_planner_v2',
    });

    history.sort((a, b) => {
      const dateA = String(a.fechaCambio || a.fecha_cambio || a.fecha || '');
      const dateB = String(b.fechaCambio || b.fecha_cambio || b.fecha || '');
      return dateB.localeCompare(dateA);
    });

    const updatePayload: any = {
      estado: 'en progreso',
      fecha_solucion: dueDateIso,
      fecha_en_progreso: nowIso,
      historial_fechas: history,
      motivo_cambio: trimmedReason,
    };

    const updateTicket$ = () =>
      this.ticketService.updateTicket(ticket.ticket_id, updatePayload);

    if (!ticket.refaccion_definida_por_jefe) {
      return updateTicket$();
    }

    return this.ticketService
      .setCompromiso(ticket.ticket_id, {
        fecha_solucion: dueDateIso,
        necesita_refaccion: ticket.necesita_refaccion,
        descripcion_refaccion: ticket.necesita_refaccion
          ? ticket.descripcion_refaccion
          : null,
        refaccion_definida_por_jefe: true,
      })
      .pipe(switchMap(() => updateTicket$()));
  }

  private toCommitmentIso(value: string): string {
    const [year, month, day] = value.split('-').map(Number);
    if (!year || !month || !day) {
      throw new Error('Fecha de compromiso inválida.');
    }

    return new Date(year, month - 1, day, 7, 0, 0).toISOString();
  }
}
