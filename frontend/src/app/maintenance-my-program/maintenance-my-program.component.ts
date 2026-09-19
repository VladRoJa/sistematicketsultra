import { CommonModule } from '@angular/common';
import { Component, OnInit, inject } from '@angular/core';

import {
  MaintenanceMyProgram,
  MaintenanceMyProgramItem,
  MaintenancePreventiveService,
} from '../services/maintenance-preventive.service';

type ProgramView = 'today' | 'week' | 'overdue' | 'pending';

@Component({
  selector: 'app-maintenance-my-program',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './maintenance-my-program.component.html',
  styleUrls: ['./maintenance-my-program.component.css'],
})
export class MaintenanceMyProgramComponent implements OnInit {
  private readonly service = inject(MaintenancePreventiveService);

  program: MaintenanceMyProgram | null = null;
  activeView: ProgramView = 'today';
  loading = false;
  errorMessage = '';

  ngOnInit(): void {
    this.loadProgram();
  }

  get visibleItems(): MaintenanceMyProgramItem[] {
    if (!this.program) return [];

    switch (this.activeView) {
      case 'week':
        return this.program.week_items;
      case 'overdue':
        return this.program.overdue;
      case 'pending':
        return this.program.pending_validation;
      case 'today':
      default:
        return this.program.today_items;
    }
  }

  get activeTitle(): string {
    const titles: Record<ProgramView, string> = {
      today: 'Hoy',
      week: 'Esta semana',
      overdue: 'Vencidos',
      pending: 'Pendientes de validación',
    };
    return titles[this.activeView];
  }

  loadProgram(): void {
    this.loading = true;
    this.errorMessage = '';

    this.service.getMyProgram().subscribe({
      next: (program) => {
        this.program = program;
        this.loading = false;
      },
      error: (error) => {
        this.program = null;
        this.loading = false;
        this.errorMessage =
          error?.error?.mensaje
          || error?.error?.detail
          || 'No se pudo cargar tu programa.';
      },
    });
  }

  selectView(view: ProgramView): void {
    this.activeView = view;
  }

  isSelected(view: ProgramView): boolean {
    return this.activeView === view;
  }

  statusLabel(item: MaintenanceMyProgramItem): string {
    const labels: Record<string, string> = {
      HOY: 'Hoy',
      PROGRAMADO: 'Programado',
      VENCIDO: 'Vencido',
      PENDIENTE_VALIDACION: 'Por validar',
      SIN_FECHA: 'Sin fecha',
    };
    return labels[item.operational_status] || item.operational_status;
  }

  typeLabel(item: MaintenanceMyProgramItem): string {
    return item.tipo_mantenimiento === 'PREVENTIVO'
      ? 'Preventivo'
      : 'Correctivo';
  }

  formatDate(value: string | null): string {
    if (!value) return 'Sin fecha';

    const [year, month, day] = value.split('-').map(Number);
    const date = new Date(year, (month || 1) - 1, day || 1, 12, 0, 0);

    return new Intl.DateTimeFormat('es-MX', {
      weekday: 'short',
      day: 'numeric',
      month: 'short',
    }).format(date);
  }

  trackItem(_: number, item: MaintenanceMyProgramItem): number {
    return item.ticket_id;
  }
}
