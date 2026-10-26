import { CommonModule } from '@angular/common';
import { Component, Inject } from '@angular/core';
import { MAT_DIALOG_DATA, MatDialog, MatDialogModule, MatDialogRef } from '@angular/material/dialog';

import { AsignarFechaModalComponent } from '../shared/asignar-fecha-modal/asignar-fecha-modal.component';
import {
  EditarFechaSolucionDialogResult,
  EditarFechaSolucionModalComponent,
} from '../shared/editar-fecha-solucion-modal/editar-fecha-solucion-modal.component';
import { ModalCierreTicketComponent } from '../shared/modal-cierre-ticket/modal-cierre-ticket.component';
import {
  MaintenanceWorkAction,
  MaintenanceWorkActionDialogComponent,
} from '../shared/maintenance-work-action-dialog/maintenance-work-action-dialog.component';
import {
  MaintenanceAssignee,
  MaintenanceCoordinationService,
} from '../services/maintenance-coordination.service';
import { AsignarFechaPayload } from '../types/ticket';
import {
  MaintenancePlannerHistoryItem,
  MaintenancePlannerService,
  MaintenancePlannerTicket,
} from './maintenance-planner.service';

export interface MaintenancePlannerTicketDialogData {
  ticket: MaintenancePlannerTicket;
  canSchedule: boolean;
  canCaptureDiagnosis: boolean;
  canRequestClosure: boolean;
  canSelfManage: boolean;
  initialDate?: string | null;
}

@Component({
  selector: 'app-maintenance-planner-ticket-dialog',
  standalone: true,
  imports: [CommonModule, MatDialogModule, AsignarFechaModalComponent],
  templateUrl: './maintenance-planner-ticket-dialog.component.html',
  styleUrls: ['./maintenance-planner-ticket-dialog.component.css'],
})
export class MaintenancePlannerTicketDialogComponent {
  readonly ticket = this.data.ticket;
  readonly canSchedule = this.data.canSchedule;
  readonly canCaptureDiagnosis = this.data.canCaptureDiagnosis;
  readonly canRequestClosure = this.data.canRequestClosure;
  readonly canSelfManage = this.data.canSelfManage;
  // El diagnóstico técnico requiere un flujo distinto; coordinación usa el PUT transaccional de Tickets V1.
  readonly useCoordinatedAssignment = this.canRequestClosure && !this.canCaptureDiagnosis;
  readonly commitmentTicket = {
    ...this.data.ticket,
    id: this.data.ticket.ticket_id,
    departamento_id: 1,
    departamento_nombre: 'Mantenimiento',
  };

  readonly initialCommitmentDate = this.parseCommitmentDate(
    this.ticket.fecha_solucion_date ? null : this.data.initialDate,
  );

  saving = false;
  errorMessage = '';
  coordinationLoading = false;
  coordinationReady = false;
  coordinationError = '';
  responsablesMantenimiento: MaintenanceAssignee[] = [];

  constructor(
    @Inject(MAT_DIALOG_DATA)
    readonly data: MaintenancePlannerTicketDialogData,
    private readonly dialogRef: MatDialogRef<MaintenancePlannerTicketDialogComponent>,
    private readonly dialog: MatDialog,
    private readonly plannerService: MaintenancePlannerService,
    private readonly maintenanceCoordinationService: MaintenanceCoordinationService,
  ) {
    if (this.useCoordinatedAssignment && this.canAssignInitialCommitment) {
      this.loadCoordinationContext();
    }
  }

  get canShowInitialCommitmentForm(): boolean {
    return !this.useCoordinatedAssignment || this.coordinationReady;
  }

  private loadCoordinationContext(): void {
    this.coordinationLoading = true;
    this.maintenanceCoordinationService.getContext().subscribe({
      next: (context) => {
        this.coordinationLoading = false;
        if (!context.can_coordinate) {
          this.coordinationError = 'Tu perfil no tiene permiso para asignar responsables de Mantenimiento.';
          return;
        }
        this.responsablesMantenimiento = context.assignees || [];
        this.coordinationReady = true;
      },
      error: () => {
        this.coordinationLoading = false;
        this.coordinationError = 'No se pudo cargar el catálogo de responsables. Cierra y vuelve a abrir el ticket.';
      },
    });
  }

  get hasCommitment(): boolean {
    return Boolean(this.ticket.fecha_solucion || this.ticket.fecha_solucion_date);
  }

  get normalizedState(): string {
    return String(this.ticket.estado || '').trim().toLowerCase();
  }

  get canAssignInitialCommitment(): boolean {
    return Boolean(
      this.canSchedule
      && !this.hasCommitment
      && ['abierto', 'en progreso'].includes(this.normalizedState),
    );
  }

  get canReprogramCommitment(): boolean {
    return Boolean(
      this.canSchedule
      && this.hasCommitment
      && this.normalizedState === 'en progreso',
    );
  }

  get tapizadoBloqueaCierre(): boolean {
    if (this.ticket.tipo_trabajo !== 'TAPIZADO') return false;
    const avance = this.ticket.avance_tapizado;
    return !avance || avance.total < 1 || avance.completo !== true;
  }

  get mostrarAvisoTapizadoIncompleto(): boolean {
    return this.canRequestClosure
      && this.normalizedState === 'en progreso'
      && this.tapizadoBloqueaCierre;
  }

  get mensajeTapizadoIncompleto(): string {
    const avance = this.ticket.avance_tapizado;
    return avance && avance.total > 0
      ? `Tapizado: ${avance.recibidos}/${avance.total} recibidos. Faltan ${avance.pendientes} por recibir para habilitar el cierre.`
      : 'Registra los aparatos y sus recepciones antes de solicitar el cierre.';
  }

  get canFinalizeTicket(): boolean {
    return Boolean(
      !this.tapizadoBloqueaCierre
      && this.canRequestClosure
      && this.normalizedState === 'en progreso'
      && (
        this.ticket.tipo_atencion === 'EXTERNA'
        || (
          this.ticket.tipo_atencion === 'AUTOGESTION'
          && this.canSelfManage
        )
        || (
          this.ticket.tipo_atencion === 'INTERNA'
          && this.ticket.estado_cierre === 'pendiente_revision_coord'
        )
        || (
          // Captura propia del jefe MANTENIMIENTO (sin técnico delegado).
          this.canCaptureDiagnosis
          && !this.ticket.tipo_atencion
          && !this.ticket.asignado_a
        )
      ),
    );
  }

  get canMarkWorkCompleted(): boolean {
    return Boolean(this.ticket.can_mark_work_completed && this.normalizedState === 'en progreso');
  }

  get canReturnWork(): boolean {
    return Boolean(
      this.canRequestClosure
      && this.normalizedState === 'en progreso'
      && this.ticket.tipo_atencion === 'INTERNA'
      && this.ticket.estado_cierre === 'pendiente_revision_coord',
    );
  }

  get closureActionLabel(): string {
    return this.ticket.tipo_atencion === 'INTERNA'
      ? 'Revisar y solicitar cierre'
      : 'Solicitar cierre';
  }

  get closureStageLabel(): string {
    if (this.ticket.estado_cierre === 'pendiente_revision_coord') {
      return 'Trabajo terminado · Pendiente de revisión de coordinación';
    }
    if (this.ticket.estado_cierre === 'pendiente_creador') {
      return 'Cierre pendiente de conformidad del gerente';
    }
    return this.ticket.estado_cierre || 'Sin flujo de cierre activo';
  }

  get history(): MaintenancePlannerHistoryItem[] {
    return [...(this.ticket.historial_fechas || [])].sort((a, b) => {
      const dateA = this.historyTimestamp(a);
      const dateB = this.historyTimestamp(b);
      return dateB.localeCompare(dateA);
    });
  }

  saveInitialCommitment(event: AsignarFechaPayload): void {
    if (!this.canAssignInitialCommitment || this.saving) {
      return;
    }

    if (this.useCoordinatedAssignment && (
      !this.coordinationReady
      || !event.tipo_atencion
      || (event.tipo_atencion === 'INTERNA' && !event.asignado_user_id)
    )) {
      this.errorMessage = 'Selecciona el tipo de atención y un responsable interno cuando corresponda.';
      return;
    }

    // Para coordinación, fecha y asignación se guardan juntas y con historial.
    // No usar scheduleTicket(): esa ruta únicamente registra el compromiso.
    const fecha = event.fecha;
    const dueDate = [
      fecha.getFullYear(),
      String(fecha.getMonth() + 1).padStart(2, '0'),
      String(fecha.getDate()).padStart(2, '0'),
    ].join('-');
    const request$ = this.useCoordinatedAssignment
      ? this.maintenanceCoordinationService.coordinateTicket(this.ticket.ticket_id, {
          due_date: dueDate,
          motivo: event.motivo.trim(),
          tipo_atencion: event.tipo_atencion!,
          asignado_user_id: event.tipo_atencion === 'INTERNA'
            ? (event.asignado_user_id ?? null)
            : null,
          ...(event.necesita_refaccion !== undefined
            ? { necesita_refaccion: !!event.necesita_refaccion }
            : {}),
          ...(event.descripcion_refaccion !== undefined
            ? { descripcion_refaccion: event.descripcion_refaccion }
            : {}),
        })
      : this.plannerService.assignInitialCommitmentFromForm(
          this.ticket,
          event,
          this.canCaptureDiagnosis,
        );

    this.saving = true;
    this.errorMessage = '';

    request$.subscribe({
        next: () => {
          this.saving = false;
          this.dialogRef.close({ updated: true });
        },
        error: (error) => {
          this.saving = false;
          this.errorMessage =
            error?.error?.mensaje
            || error?.error?.message
            || 'No se pudo asignar el compromiso del ticket.';
        },
      });
  }

  openRescheduleDialog(): void {
    if (!this.canReprogramCommitment || this.saving) {
      return;
    }

    const dialogRef = this.dialog.open<
      EditarFechaSolucionModalComponent,
      { fechaActual: string | null },
      EditarFechaSolucionDialogResult | undefined
    >(EditarFechaSolucionModalComponent, {
      width: '560px',
      maxWidth: '92vw',
      data: { fechaActual: this.ticket.fecha_solucion },
      autoFocus: false,
    });

    dialogRef.afterClosed().subscribe((result) => {
      if (!result?.fecha || !result.motivo) {
        return;
      }

      this.saving = true;
      this.errorMessage = '';

      this.plannerService
        .reprogramCommitmentFromDate(
          this.ticket,
          result.fecha,
          result.motivo,
        )
        .subscribe({
          next: () => {
            this.saving = false;
            this.dialogRef.close({ updated: true });
          },
          error: (error) => {
            this.saving = false;
            this.errorMessage =
              error?.error?.mensaje
              || error?.error?.message
              || 'No se pudo cambiar la fecha compromiso.';
          },
        });
    });
  }

  openWorkActionDialog(action: MaintenanceWorkAction): void {
    const permitted = action === 'complete'
      ? this.canMarkWorkCompleted
      : this.canReturnWork;
    if (!permitted || this.saving) return;

    const ref = this.dialog.open(MaintenanceWorkActionDialogComponent, {
      width: '520px',
      maxWidth: '94vw',
      data: { ticketId: this.ticket.ticket_id, action },
      autoFocus: false,
    });

    ref.afterClosed().subscribe((notes: string | null) => {
      if (!notes) return;
      this.saving = true;
      this.errorMessage = '';
      const actionRequest = action === 'complete'
        ? this.maintenanceCoordinationService.markWorkCompleted(this.ticket.ticket_id, notes)
        : this.maintenanceCoordinationService.returnWorkToTechnician(this.ticket.ticket_id, notes);
      actionRequest.subscribe({
        next: () => {
          this.saving = false;
          this.dialogRef.close({ updated: true });
        },
        error: (error) => {
          this.saving = false;
          this.errorMessage =
            error?.error?.mensaje || 'No fue posible guardar la acción de Mantenimiento.';
        },
      });
    });
  }

  openClosureDialog(): void {
    if (!this.canFinalizeTicket || this.saving) {
      return;
    }

    const dialogRef = this.dialog.open(ModalCierreTicketComponent, {
      width: '560px',
      maxWidth: '92vw',
      data: { ticketId: this.ticket.ticket_id, modo: 'maintenance_request' },
      autoFocus: false,
    });

    dialogRef.afterClosed().subscribe((result) => {
      if (!result) {
        return;
      }

      this.saving = true;
      this.errorMessage = '';

      this.plannerService
        .requestClosure(this.ticket, {
          costo_solucion: result.costo,
          notas_cierre: result.notas,
        })
        .subscribe({
          next: () => {
            this.saving = false;
            this.dialogRef.close({ updated: true });
          },
          error: (error) => {
            this.saving = false;
            this.errorMessage =
              error?.error?.mensaje
              || error?.error?.message
              || 'No se pudo solicitar el cierre del ticket.';
          },
        });
    });
  }

  close(): void {
    this.dialogRef.close({ updated: false });
  }

  historyTargetDate(item: MaintenancePlannerHistoryItem): string | null {
    return String(item.fecha || item.fecha_solucion || '').trim() || null;
  }

  historyChangedAt(item: MaintenancePlannerHistoryItem): string | null {
    return String(item.fechaCambio || item.fecha_cambio || '').trim() || null;
  }

  historyUser(item: MaintenancePlannerHistoryItem): string {
    return String(
      item.cambiadoPor
      || item.usuario
      || item.username
      || '—'
    );
  }

  historyReason(item: MaintenancePlannerHistoryItem): string {
    return String(
      item.motivo
      || item.comentario
      || item.razon
      || 'Sin comentario'
    );
  }

  formatDateTime(value: string | null | undefined): string {
    if (!value) return '—';
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return value;

    return new Intl.DateTimeFormat('es-MX', {
      dateStyle: 'medium',
      timeStyle: 'short',
      timeZone: 'America/Tijuana',
    }).format(date);
  }

  formatDate(value: string | null | undefined): string {
    if (!value) return '—';
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return value;

    return new Intl.DateTimeFormat('es-MX', {
      dateStyle: 'medium',
      timeZone: 'America/Tijuana',
    }).format(date);
  }

  private historyTimestamp(item: MaintenancePlannerHistoryItem): string {
    return String(
      item.fechaCambio
      || item.fecha_cambio
      || item.fecha
      || item.fecha_solucion
      || ''
    );
  }

  private parseCommitmentDate(value: string | null | undefined): Date | null {
    if (!value) {
      return null;
    }

    const [year, month, day] = value.split('-').map(Number);
    if (!year || !month || !day) {
      return null;
    }

    return new Date(year, month - 1, day, 7, 0, 0);
  }
}
