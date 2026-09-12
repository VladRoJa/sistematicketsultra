import { CommonModule } from '@angular/common';
import { Component, OnInit, inject } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MaintenancePlannerBoard, MaintenancePlannerService, MaintenancePlannerTicket } from './maintenance-planner.service';

@Component({
  selector: 'app-maintenance-planner',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './maintenance-planner.component.html',
  styleUrls: ['./maintenance-planner.component.css'],
})
export class MaintenancePlannerComponent implements OnInit {
  private readonly plannerService = inject(MaintenancePlannerService);

  board: MaintenancePlannerBoard | null = null;
  loading = false;
  errorMessage = '';

  branchId: number | null = null;
  estado = 'todos';
  selectedTicket: MaintenancePlannerTicket | null = null;
  scheduleDate = '';
  scheduleReason = '';
  savingSchedule = false;

  weekStart = this.getMonday(new Date());

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
        if (
          this.selectedTicket &&
          !this.findTicketById(this.selectedTicket.ticket_id)
        ) {
          this.clearSelection();
        }
      },
      error: (error) => {
        this.loading = false;
        this.board = null;
        this.errorMessage =
          error?.error?.mensaje || 'No se pudo cargar el Planner de Mantenimiento.';
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
    this.weekStart = this.getMonday(new Date());
    this.loadBoard();
  }

  nextWeek(): void {
    const date = new Date(this.weekStart);
    date.setDate(date.getDate() + 7);
    this.weekStart = date;
    this.loadBoard();
  }

  onFiltersChanged(): void {
    this.clearSelection();
    this.loadBoard();
  }

  selectTicket(ticket: MaintenancePlannerTicket): void {
    this.selectedTicket = ticket;
    this.scheduleDate = ticket.fecha_solucion_date || this.toDateOnly(new Date());
    this.scheduleReason = '';
  }

  clearSelection(): void {
    this.selectedTicket = null;
    this.scheduleDate = '';
    this.scheduleReason = '';
  }

  saveSchedule(): void {
    if (!this.selectedTicket || !this.scheduleDate || !this.scheduleReason.trim()) {
      return;
    }

    this.savingSchedule = true;
    this.errorMessage = '';
    this.plannerService.scheduleTicket(this.selectedTicket.ticket_id, {
      due_date: this.scheduleDate,
      reason: this.scheduleReason.trim(),
    }).subscribe({
      next: () => {
        this.savingSchedule = false;
        const selectedId = this.selectedTicket?.ticket_id ?? null;
        this.loadBoard();
        if (selectedId) {
          setTimeout(() => {
            const refreshed = this.findTicketById(selectedId);
            if (refreshed) this.selectTicket(refreshed);
          });
        }
      },
      error: (error) => {
        this.savingSchedule = false;
        this.errorMessage = error?.error?.mensaje || 'No se pudo guardar la fecha compromiso.';
      },
    });
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
    return new Intl.DateTimeFormat('es-MX', { weekday: 'short', day: 'numeric' }).format(date);
  }

  formatRange(): string {
    const formatter = new Intl.DateTimeFormat('es-MX', { day: 'numeric', month: 'short' });
    return `${formatter.format(this.weekStart)} – ${formatter.format(this.weekEnd)}`;
  }

  trackTicket(_: number, ticket: MaintenancePlannerTicket): number {
    return ticket.ticket_id;
  }

  private findTicketById(ticketId: number): MaintenancePlannerTicket | null {
    if (!this.board) return null;
    const sources = [
      ...this.board.overdue,
      ...this.board.unscheduled,
      ...this.board.today_items,
      ...this.board.future,
      ...this.board.days.flatMap((day) => day.items),
    ];
    return sources.find((ticket) => ticket.ticket_id === ticketId) || null;
  }

  private getMonday(source: Date): Date {
    const date = new Date(source.getFullYear(), source.getMonth(), source.getDate());
    const day = date.getDay();
    const diff = day === 0 ? -6 : 1 - day;
    date.setDate(date.getDate() + diff);
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
