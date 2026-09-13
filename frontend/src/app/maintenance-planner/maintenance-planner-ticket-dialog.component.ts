import { CommonModule } from '@angular/common';
import { Component, Inject } from '@angular/core';
import { MAT_DIALOG_DATA, MatDialog, MatDialogModule, MatDialogRef } from '@angular/material/dialog';

import { AsignarFechaModalComponent } from '../shared/asignar-fecha-modal/asignar-fecha-modal.component';
import {
  EditarFechaSolucionDialogResult,
  EditarFechaSolucionModalComponent,
} from '../shared/editar-fecha-solucion-modal/editar-fecha-solucion-modal.component';
import { ModalCierreTicketComponent } from '../shared/modal-cierre-ticket/modal-cierre-ticket.component';
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

  constructor(
    @Inject(MAT_DIALOG_DATA)
    readonly data: MaintenancePlannerTicketDialogData,
    private readonly dialogRef: MatDialogRef<MaintenancePlannerTicketDialogComponent>,
    private readonly dialog: MatDialog,
    private readonly plannerService: MaintenancePlannerService,
  ) {}

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

  get canFinalizeTicket(): boolean {
    return Boolean(
      this.canRequestClosure
      && this.normalizedState === 'en progreso'
      && this.ticket.estado_cierre !== 'pendiente_creador',
    );
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

    this.saving = true;
    this.errorMessage = '';

    this.plannerService
      .assignInitialCommitmentFromForm(
        this.ticket,
        event,
        this.canCaptureDiagnosis,
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

  openClosureDialog(): void {
    if (!this.canFinalizeTicket || this.saving) {
      return;
    }

    const dialogRef = this.dialog.open(ModalCierreTicketComponent, {
      width: '560px',
      maxWidth: '92vw',
      data: { ticketId: this.ticket.ticket_id },
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
