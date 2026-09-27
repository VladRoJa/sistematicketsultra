import { HttpClient, HttpParams } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable, switchMap } from 'rxjs';

import { MantenimientoEquiposService } from '../services/mantenimiento-equipos.service';
import { MaintenancePreventiveService } from '../services/maintenance-preventive.service';
import { TicketService } from '../services/ticket.service';
import { AsignarFechaPayload } from '../types/ticket';
import { environment } from 'src/environments/environment';

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
  condicion_operativa: 'TRABAJA' | 'NO_TRABAJA' | null;
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
    can_reprogram: boolean;
    can_capture_diagnosis: boolean;
    can_request_closure: boolean;
  };
}

@Injectable({ providedIn: 'root' })
export class MaintenancePlannerService {
  private readonly http = inject(HttpClient);
  private readonly ticketService = inject(TicketService);
  private readonly mantenimientoEquiposService = inject(MantenimientoEquiposService);
  private readonly maintenancePreventiveService = inject(MaintenancePreventiveService);
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

  scheduleTicket(
    ticketId: number,
    payload: { due_date: string; reason: string },
  ): Observable<{ mensaje: string; ticket: unknown }> {
    return this.http.put<{ mensaje: string; ticket: unknown }>(
      `${this.baseUrl}/tickets/${ticketId}/schedule`,
      payload,
    );
  }

  /** Primera asignación de compromiso: equivale al flujo En progreso de Tickets. */
  assignInitialCommitmentFromForm(
    ticket: MaintenancePlannerTicket,
    event: AsignarFechaPayload,
    canCaptureDiagnosis: boolean,
  ): Observable<unknown> {
    if (ticket.fecha_solucion || ticket.fecha_solucion_date) {
      throw new Error(
        'El ticket ya tiene fecha compromiso. Usa el flujo de reprogramación.',
      );
    }

    const reason = String(event.motivo || '').trim();
    if (!event.fecha || !reason) {
      throw new Error('La fecha y el motivo son obligatorios.');
    }

    const dueDateIso = this.toCommitmentIsoFromDate(event.fecha);

    if (canCaptureDiagnosis && Number(ticket.aparato_id) > 0) {
      return this.mantenimientoEquiposService.guardarCompromiso(
        ticket.ticket_id,
        {
          fecha_solucion: dueDateIso,
          motivo: reason,
          falla_mantenimiento_id: event.falla_mantenimiento_id,
          condicion_operativa: event.condicion_operativa,
          necesita_refaccion: !!event.necesita_refaccion,
          descripcion_refaccion: event.necesita_refaccion
            ? (event.descripcion_refaccion || '')
            : '',
        },
      );
    }

    const dueDate = this.toDateOnly(event.fecha);
    const schedule$ = () =>
      this.scheduleTicket(ticket.ticket_id, {
        due_date: dueDate,
        reason,
      });

    if (!event.refaccion_definida_por_jefe) {
      return schedule$();
    }

    return this.ticketService
      .setCompromiso(ticket.ticket_id, {
        fecha_solucion: dueDateIso,
        necesita_refaccion: !!event.necesita_refaccion,
        descripcion_refaccion: event.necesita_refaccion
          ? (event.descripcion_refaccion || '')
          : null,
        refaccion_definida_por_jefe: true,
      })
      .pipe(switchMap(() => schedule$()));
  }

  /** Reprogramación auditada: usa catálogo y endpoint canónico de Mantenimiento. */
  reprogramCommitment(
    ticket: MaintenancePlannerTicket,
    dueDate: string,
    reasonId: number,
    comentario?: string | null,
  ): Observable<unknown> {
    this.assertReprogrammable(ticket);

    return this.maintenancePreventiveService.reprogramMaintenanceTicket(
      ticket.ticket_id,
      {
        nueva_fecha: dueDate,
        reason_id: reasonId,
        comentario: comentario || null,
      },
    );
  }

  reprogramCommitmentFromDate(
    ticket: MaintenancePlannerTicket,
    dueDate: Date,
    reasonId: number,
    comentario?: string | null,
  ): Observable<unknown> {
    return this.reprogramCommitment(
      ticket,
      this.toDateOnly(dueDate),
      reasonId,
      comentario,
    );
  }

  /** Solicitud de cierre usando exactamente el endpoint de la pantalla de Tickets. */
  requestClosure(
    ticket: MaintenancePlannerTicket,
    payload: { costo_solucion: number | null; notas_cierre: string | null },
  ): Observable<unknown> {
    const state = String(ticket.estado || '').trim().toLowerCase();
    if (state !== 'en progreso') {
      throw new Error('Solo se puede finalizar un ticket que esté en progreso.');
    }

    return this.ticketService.cierreSolicitar(ticket.ticket_id, payload);
  }

  private assertReprogrammable(ticket: MaintenancePlannerTicket): void {
    const hasCommitment = Boolean(ticket.fecha_solucion || ticket.fecha_solucion_date);
    const state = String(ticket.estado || '').trim().toLowerCase();

    if (!hasCommitment) {
      throw new Error(
        'El ticket todavía no tiene compromiso. Primero debes asignar la fecha inicial.',
      );
    }
    if (state !== 'en progreso') {
      throw new Error(
        'Solo se puede reprogramar un ticket que esté en progreso.',
      );
    }
  }

  private toCommitmentIsoFromDate(value: Date): string {
    return new Date(
      value.getFullYear(),
      value.getMonth(),
      value.getDate(),
      7,
      0,
      0,
    ).toISOString();
  }

  private toDateOnly(value: Date): string {
    const year = value.getFullYear();
    const month = String(value.getMonth() + 1).padStart(2, '0');
    const day = String(value.getDate()).padStart(2, '0');
    return `${year}-${month}-${day}`;
  }
}
