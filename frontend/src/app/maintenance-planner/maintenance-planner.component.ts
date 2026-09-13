import { CdkDragDrop, DragDropModule } from '@angular/cdk/drag-drop';
import { CommonModule } from '@angular/common';
import { Component, OnInit, inject } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatDialog } from '@angular/material/dialog';

import {
  EditarFechaSolucionDialogResult,
  EditarFechaSolucionModalComponent,
} from '../shared/editar-fecha-solucion-modal/editar-fecha-solucion-modal.component';
import {
  MaintenancePlannerBoard,
  MaintenancePlannerDay,
  MaintenancePlannerService,
  MaintenancePlannerTicket,
} from './maintenance-planner.service';
import { MaintenancePlannerTicketDialogComponent } from './maintenance-planner-ticket-dialog.component';

type PlannerFocusMode =
  | 'priority'
  | 'overdue'
  | 'today'
  | 'week'
  | 'unscheduled'
  | 'spare_parts'
  | 'active';

@Component({
  selector: 'app-maintenance-planner',
  standalone: true,
  imports: [CommonModule, FormsModule, DragDropModule],
  templateUrl: './maintenance-planner.component.html',
  styleUrls: [
    './maintenance-planner.component.css',
    './maintenance-planner.compact-header.css',
  ],
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
  estado = 'activos';
  focusMode: PlannerFocusMode = 'priority';
  focusVisibleLimit = 12;

  weekStart = this.getSunday(new Date());

  readonly estados = [
    { value: 'activos', label: 'Activos' },
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

  get focusTitle(): string {
    const titles: Record<PlannerFocusMode, string> = {
      priority: 'Resolver en junta',
      overdue: 'Tickets vencidos',
      today: 'Para hoy',
      week: 'En la semana',
      unscheduled: 'Sin fecha compromiso',
      spare_parts: 'Con refacción',
      active: 'Tickets activos',
    };
    return titles[this.focusMode];
  }

  get focusDescription(): string {
    const descriptions: Record<PlannerFocusMode, string> = {
      priority: 'Prioridades: vencidos y tickets sin compromiso.',
      overdue: 'Compromisos cuya fecha ya pasó y siguen activos.',
      today: 'Tickets con compromiso para hoy.',
      week: 'Tickets ubicados en la semana visible del calendario.',
      unscheduled: 'Tickets activos que todavía no tienen fecha compromiso.',
      spare_parts: 'Tickets activos marcados como requiere refacción.',
      active: 'Universo activo con los filtros actuales.',
    };
    return descriptions[this.focusMode];
  }

  get focusItems(): MaintenancePlannerTicket[] {
    if (!this.board) return [];

    switch (this.focusMode) {
      case 'overdue':
        return this.dedupeTickets(this.board.overdue);
      case 'today':
        return this.dedupeTickets(this.board.today_items);
      case 'week':
        return this.dedupeTickets(
          this.board.days.flatMap((day) => day.items),
        );
      case 'unscheduled':
        return this.dedupeTickets(this.board.unscheduled);
      case 'spare_parts':
        return this.allActiveItems.filter((ticket) => ticket.necesita_refaccion);
      case 'active':
        return this.allActiveItems;
      case 'priority':
      default:
        return this.dedupeTickets([
          ...this.board.overdue,
          ...this.board.unscheduled,
        ]);
    }
  }

  get visibleFocusItems(): MaintenancePlannerTicket[] {
    return this.focusItems.slice(0, this.focusVisibleLimit);
  }

  get focusTotal(): number {
    return this.focusItems.length;
  }

  get focusBaseLimit(): number {
    return this.defaultFocusLimit(this.focusMode);
  }

  get allActiveItems(): MaintenancePlannerTicket[] {
    if (!this.board) return [];
    return this.dedupeTickets([
      ...this.board.overdue,
      ...this.board.today_items,
      ...this.board.future,
      ...this.board.unscheduled,
    ]);
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
        this.focusVisibleLimit = this.defaultFocusLimit(this.focusMode);
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

  selectFocus(mode: PlannerFocusMode): void {
    this.focusMode = mode;
    this.focusVisibleLimit = this.defaultFocusLimit(mode);
  }

  isFocusSelected(mode: PlannerFocusMode): boolean {
    return this.focusMode === mode;
  }

  showMoreFocus(): void {
    this.focusVisibleLimit += 24;
  }

  showLessFocus(): void {
    this.focusVisibleLimit = this.defaultFocusLimit(this.focusMode);
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
        canRequestClosure: Boolean(
          this.board?.permissions.can_request_closure,
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

    this.errorMessage = '';

    const dialogRef = this.dialog.open<
      EditarFechaSolucionModalComponent,
      { fechaActual: string | null },
      EditarFechaSolucionDialogResult | undefined
    >(EditarFechaSolucionModalComponent, {
      width: '560px',
      maxWidth: '92vw',
      data: { fechaActual: targetDay.date },
      autoFocus: false,
      restoreFocus: false,
    });

    dialogRef.afterClosed().subscribe((result) => {
      if (!result?.fecha || !result.motivo) {
        return;
      }

      this.dragSavingTicketId = ticket.ticket_id;
      this.errorMessage = '';

      this.plannerService
        .reprogramCommitmentFromDate(ticket, result.fecha, result.motivo)
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
              || 'No se pudo reprogramar el compromiso.';
            this.loadBoard();
          },
        });
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

  focusMeta(ticket: MaintenancePlannerTicket): string {
    const dueDate = ticket.fecha_solucion_date;

    if (ticket.planner_status === 'VENCIDO') {
      const lateDays = this.daysOverdue(ticket);
      if (!dueDate) return 'Vencido';
      return `${this.formatDateOnly(dueDate)}${lateDays > 0 ? ` · ${lateDays} ${lateDays === 1 ? 'día' : 'días'} de atraso` : ''}`;
    }

    if (ticket.planner_status === 'SIN_FECHA') {
      return 'Sin fecha compromiso';
    }

    if (ticket.planner_status === 'HOY') {
      return 'Compromiso hoy';
    }

    if (ticket.planner_status === 'PROGRAMADO' && dueDate) {
      return `Compromiso ${this.formatDateOnly(dueDate)}`;
    }

    if (ticket.planner_status === 'FINALIZADO') {
      return 'Finalizado';
    }

    return '';
  }

  formatDay(dateIso: string): string {
    const date = this.parseDateOnly(dateIso);
    return new Intl.DateTimeFormat('es-MX', {
      weekday: 'short',
      day: 'numeric',
    }).format(date);
  }

  formatDateOnly(dateIso: string): string {
    const date = this.parseDateOnly(dateIso);
    return new Intl.DateTimeFormat('es-MX', {
      day: 'numeric',
      month: 'short',
      year: 'numeric',
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

  private defaultFocusLimit(mode: PlannerFocusMode): number {
    return mode === 'priority' ? 12 : 24;
  }

  private dedupeTickets(
    tickets: MaintenancePlannerTicket[],
  ): MaintenancePlannerTicket[] {
    const seen = new Set<number>();
    const result: MaintenancePlannerTicket[] = [];

    for (const ticket of tickets || []) {
      if (seen.has(ticket.ticket_id)) continue;
      seen.add(ticket.ticket_id);
      result.push(ticket);
    }

    return result;
  }

  private daysOverdue(ticket: MaintenancePlannerTicket): number {
    if (!ticket.fecha_solucion_date || !this.board?.window.today) {
      return 0;
    }

    const due = this.parseDateOnly(ticket.fecha_solucion_date);
    const today = this.parseDateOnly(this.board.window.today);
    const dueUtc = Date.UTC(due.getFullYear(), due.getMonth(), due.getDate());
    const todayUtc = Date.UTC(today.getFullYear(), today.getMonth(), today.getDate());

    return Math.max(0, Math.floor((todayUtc - dueUtc) / 86400000));
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
