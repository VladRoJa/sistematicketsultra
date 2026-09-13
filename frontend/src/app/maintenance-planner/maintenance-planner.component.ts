import { CdkDragDrop, DragDropModule, transferArrayItem } from '@angular/cdk/drag-drop';
import { CommonModule } from '@angular/common';
import { Component, OnInit, inject } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatDialog } from '@angular/material/dialog';

import {
  MaintenancePlannerBoard,
  MaintenancePlannerDay,
  MaintenancePlannerService,
  MaintenancePlannerTicket,
} from './maintenance-planner.service';
import { MaintenancePlannerTicketDialogComponent } from './maintenance-planner-ticket-dialog.component';

@Component({
  selector: 'app-maintenance-planner',
  standalone: true,
  imports: [CommonModule, FormsModule, DragDropModule],
  templateUrl: './maintenance-planner.component.html',
  styleUrls: ['./maintenance-planner.component.css'],
})
export class MaintenancePlannerComponent implements OnInit {
  private readonly plannerService = inject(MaintenancePlannerService);
  private readonly dialog = inject(MatDialog);
  private suppressOpenUntil = 0;

  board: MaintenancePlannerBoard | null = null;
  loading = false;
  errorMessage = '';
  dragSavingTicketId: number | null = null;

  branchId: number | null = null;
  estado = 'todos';

  weekStart = this.getSunday(new Date());

  readonly estados = [
    { value: 'todos', label: 'Activos y cerrados' },
    { value: 'abierto', label: 'Abiertos' },
    { value: 'en progreso', label: 'En progreso' },
    { value: 'por_validar', label: 'Por validar' },
    { value: 'finalizado', label: 'Finalizados' },
  ];

  ngOnInit(): void {
    this.loadBoard();
  }

  get weekEnd(): Date {
    const end = new Date(this.weekStart);
    end.setDate(end.getDate() + 6);
    return end;
  }

  get meetingFocusItems(): MaintenancePlannerTicket[] {
    if (!this.board) return [];
    return [...this.board.overdue, ...this.board.unscheduled].slice(0, 12);
  }

  get dayDropListIds(): string[] {
    return (this.board?.days || []).map((day) => this.dropListId(day));
  }

  loadBoard(): void {
    this.loading = true;
    this.errorMessage = '';

    this.plannerService.getBoard({
      startDate: this.toDateOnly(this.weekStart),
      endDate: this.toDateOnly(this.weekEnd),
      branchId: this.branchId,
      estado: this.estado,
    }).subscribe({
      next: (board) => {
        this.board = board;
        this.loading = false;
      },
      error: (error) => {
        this.loading = false;
        this.board = null;
        this.errorMessage =
          error?.error?.mensaje
          || error?.error?.message
          || 'No se pudo cargar el Planner de Mantenimiento.';
      },
    });
  }

  previousWeek(): void {
    const date = new Date(this.weekStart);
    date.setDate(date.getDate() - 7);
    this.weekStart = date;
    this.loadBoard();
  }

  currentWeek(): void {
    this.weekStart = this.getSunday(new Date());
    this.loadBoard();
  }

  nextWeek(): void {
    const date = new Date(this.weekStart);
    date.setDate(date.getDate() + 7);
    this.weekStart = date;
    this.loadBoard();
  }

  onFiltersChanged(): void {
    this.loadBoard();
  }

  openTicket(ticket: MaintenancePlannerTicket, initialDate?: string | null): void {
    if (Date.now() < this.suppressOpenUntil) {
      return;
    }

    const dialogRef = this.dialog.open(MaintenancePlannerTicketDialogComponent, {
      data: {
        ticket,
        canSchedule: Boolean(this.board?.permissions.can_schedule),
        canCaptureDiagnosis: Boolean(
          this.board?.permissions.can_capture_diagnosis,
        ),
        initialDate: initialDate || null,
      },
      width: '1180px',
      maxWidth: '96vw',
      maxHeight: '94vh',
      autoFocus: false,
      restoreFocus: false,
      panelClass: 'maintenance-planner-ticket-dialog',
    });

    dialogRef.afterClosed().subscribe((result) => {
      if (result?.updated) {
        this.loadBoard();
      }
    });
  }

  openFirstOverdue(): void {
    const ticket = this.board?.overdue?.[0];
    if (ticket) {
      this.openTicket(ticket);
    }
  }

  dropTicket(
    event: CdkDragDrop<MaintenancePlannerTicket[]>,
    targetDay: MaintenancePlannerDay,
  ): void {
    this.suppressOpenUntil = Date.now() + 300;
    const ticket = event.item.data as MaintenancePlannerTicket;

    if (!this.canDrag(ticket)) {
      return;
    }

    const sourceDate = ticket.fecha_solucion_date;
    if (!sourceDate || sourceDate === targetDay.date) {
      return;
    }

    if (event.previousContainer !== event.container) {
      transferArrayItem(
        event.previousContainer.data,
        event.container.data,
        event.previousIndex,
        event.currentIndex,
      );
    }

    this.dragSavingTicketId = ticket.ticket_id;
    this.errorMessage = '';

    const reason = [
      'Reprogramado por arrastre en Planner',
      `${sourceDate} → ${targetDay.date}`,
    ].join(': ');

    this.plannerService
      .reprogramCommitment(ticket, targetDay.date, reason)
      .subscribe({
        next: () => {
          this.dragSavingTicketId = null;
          this.loadBoard();
        },
        error: (error) => {
          this.dragSavingTicketId = null;
          this.errorMessage =
            error?.error?.mensaje
            || error?.error?.message
            || 'No se pudo mover el compromiso. Se restauró el calendario.';
          this.loadBoard();
        },
      });
  }

  canDrag(ticket: MaintenancePlannerTicket): boolean {
    return Boolean(
      this.board?.permissions.can_schedule
      && ticket.fecha_solucion_date
      && String(ticket.estado || '').trim().toLowerCase() === 'en progreso'
      && this.dragSavingTicketId === null
    );
  }

  dropListId(day: MaintenancePlannerDay): string {
    return `maintenance-planner-${day.date}`;
  }

  statusLabel(status: MaintenancePlannerTicket['planner_status']): string {
    const labels: Record<MaintenancePlannerTicket['planner_status'], string> = {
      VENCIDO: 'Vencido',
      HOY: 'Hoy',
      PROGRAMADO: 'Programado',
      SIN_FECHA: 'Sin fecha',
      FINALIZADO: 'Finalizado',
    };
    return labels[status];
  }

  statusClass(status: MaintenancePlannerTicket['planner_status']): string {
    return `status-${status.toLowerCase().replace('_', '-')}`;
  }

  formatDay(dateIso: string): string {
    const date = this.parseDateOnly(dateIso);
    return new Intl.DateTimeFormat('es-MX', {
      weekday: 'short',
      day: 'numeric',
    }).format(date);
  }

  formatRange(): string {
    const formatter = new Intl.DateTimeFormat('es-MX', {
      day: 'numeric',
      month: 'short',
    });
    return `${formatter.format(this.weekStart)} – ${formatter.format(this.weekEnd)}`;
  }

  trackTicket(_: number, ticket: MaintenancePlannerTicket): number {
    return ticket.ticket_id;
  }

  private getSunday(source: Date): Date {
    const date = new Date(
      source.getFullYear(),
      source.getMonth(),
      source.getDate(),
    );
    date.setDate(date.getDate() - date.getDay());
    return date;
  }

  private toDateOnly(date: Date): string {
    const year = date.getFullYear();
    const month = String(date.getMonth() + 1).padStart(2, '0');
    const day = String(date.getDate()).padStart(2, '0');
    return `${year}-${month}-${day}`;
  }

  private parseDateOnly(value: string): Date {
    const [year, month, day] = value.split('-').map(Number);
    return new Date(year, (month || 1) - 1, day || 1, 12, 0, 0);
  }
}
