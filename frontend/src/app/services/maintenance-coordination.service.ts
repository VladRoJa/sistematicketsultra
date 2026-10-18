import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import { environment } from 'src/environments/environment';

export type MaintenanceAttentionMode = 'INTERNA' | 'EXTERNA';

export interface MaintenanceAssignee {
  id: number;
  username: string;
}

export interface MaintenanceCoordinationContext {
  can_coordinate: boolean;
  assignees: MaintenanceAssignee[];
}

export interface CoordinateMaintenanceTicketPayload {
  due_date: string;
  motivo: string;
  tipo_atencion: MaintenanceAttentionMode;
  asignado_user_id: number | null;
  necesita_refaccion?: boolean;
  descripcion_refaccion?: string;
}

@Injectable({ providedIn: 'root' })
export class MaintenanceCoordinationService {
  private readonly http = inject(HttpClient);
  private readonly baseUrl = `${environment.apiUrl}/tickets/maintenance`;

  getContext(): Observable<MaintenanceCoordinationContext> {
    return this.http.get<MaintenanceCoordinationContext>(
      `${this.baseUrl}/coordination/context`,
    );
  }

  coordinateTicket(
    ticketId: number,
    payload: CoordinateMaintenanceTicketPayload,
  ): Observable<{ mensaje: string; ticket: unknown }> {
    return this.http.put<{ mensaje: string; ticket: unknown }>(
      `${this.baseUrl}/${ticketId}/coordinate`,
      payload,
    );
  }
}
