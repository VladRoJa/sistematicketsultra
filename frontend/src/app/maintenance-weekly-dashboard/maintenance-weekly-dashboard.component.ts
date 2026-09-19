import { CommonModule } from '@angular/common';
import { Component, OnInit, inject } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Router } from '@angular/router';

import {
  MaintenanceDashboardDrilldown,
  MaintenanceDashboardDrilldownTicket,
  MaintenanceDashboardWeek,
  MaintenancePreventiveService,
  MaintenanceWeeklyDashboard,
} from '../services/maintenance-preventive.service';

@Component({
  selector: 'app-maintenance-weekly-dashboard',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './maintenance-weekly-dashboard.component.html',
  styleUrls: ['./maintenance-weekly-dashboard.component.css'],
})
export class MaintenanceWeeklyDashboardComponent implements OnInit {
  private readonly service = inject(MaintenancePreventiveService);
  private readonly router = inject(Router);

  dashboard: MaintenanceWeeklyDashboard | null = null;
  drilldown: MaintenanceDashboardDrilldown | null = null;
  drilldownTitle = '';

  loading = false;
  drilldownLoading = false;
  errorMessage = '';
  drilldownError = '';

  weeks = 8;
  referenceDate = '';
  regionId: number | null = null;
  branchId: number | null = null;
  crewId: number | null = null;
  responsibleUserId: number | null = null;

  ngOnInit(): void {
    this.loadDashboard();
  }

  get newestWeeks(): MaintenanceDashboardWeek[] {
    return [...(this.dashboard?.weeks || [])].reverse();
  }

  get visibleBranches() {
    const branches = this.dashboard?.context?.sucursales || [];

    if (!this.regionId) {
      return branches;
    }

    return branches.filter(
      (branch) => branch.region_id === this.regionId,
    );
  }

  get visibleCrews() {
    const crews = this.dashboard?.context?.cuadrillas || [];

    if (!this.regionId) {
      return crews;
    }

    return crews.filter(
      (crew) => crew.region_id === null || crew.region_id === this.regionId,
    );
  }

  get visibleResponsibles() {
    const rows = this.dashboard?.context?.responsables || [];

    if (!this.crewId) {
      return rows;
    }

    return rows.filter(
      (row) => row.crew_id === this.crewId,
    );
  }

  loadDashboard(): void {
    this.loading = true;
    this.errorMessage = '';
    this.closeDrilldown();

    this.service.getWeeklyDashboard({
      weeks: this.weeks,
      reference_date: this.referenceDate || undefined,
      region_id: this.regionId,
      branch_id: this.branchId,
      crew_id: this.crewId,
      responsible_user_id: this.responsibleUserId,
    }).subscribe({
      next: (dashboard) => {
        this.dashboard = dashboard;
        this.loading = false;
      },
      error: (error) => {
        this.dashboard = null;
        this.loading = false;
        this.errorMessage =
          error?.error?.mensaje
          || error?.error?.detail
          || 'No se pudo cargar el panel de Mantenimiento.';
      },
    });
  }

  onRegionChanged(): void {
    if (
      this.branchId
      && !this.visibleBranches.some(
        (branch) => branch.id === this.branchId,
      )
    ) {
      this.branchId = null;
    }

    if (
      this.crewId
      && !this.visibleCrews.some((crew) => crew.id === this.crewId)
    ) {
      this.crewId = null;
      this.responsibleUserId = null;
    }

    this.loadDashboard();
  }

  onCrewChanged(): void {
    if (
      this.responsibleUserId
      && !this.visibleResponsibles.some(
        (row) => row.user_id === this.responsibleUserId,
      )
    ) {
      this.responsibleUserId = null;
    }
    this.loadDashboard();
  }

  openDrilldown(
    week: MaintenanceDashboardWeek,
    metric: string,
    title: string,
  ): void {
    this.drilldownLoading = true;
    this.drilldownError = '';
    this.drilldown = null;
    this.drilldownTitle =
      title + ' · Semana ' + String(week.week_number);

    this.service.getDashboardDrilldown({
      week_start: week.week_start,
      metric,
      region_id: this.regionId,
      branch_id: this.branchId,
      crew_id: this.crewId,
      responsible_user_id: this.responsibleUserId,
    }).subscribe({
      next: (detail) => {
        this.drilldown = detail;
        this.drilldownLoading = false;
      },
      error: (error) => {
        this.drilldownLoading = false;
        this.drilldownError =
          error?.error?.mensaje
          || error?.error?.detail
          || 'No se pudo abrir el detalle.';
      },
    });
  }

  closeDrilldown(): void {
    this.drilldown = null;
    this.drilldownTitle = '';
    this.drilldownError = '';
    this.drilldownLoading = false;
  }

  openTicket(ticket: MaintenanceDashboardDrilldownTicket): void {
    this.router.navigate(
      ['/main/ver-tickets'],
      {
        queryParams: {
          ticket_id: ticket.id,
        },
      },
    );
  }

  formatRange(week: MaintenanceDashboardWeek): string {
    return (
      this.formatDateOnly(week.week_start)
      + ' – '
      + this.formatDateOnly(week.week_end)
    );
  }

  formatDateTime(value: string | null): string {
    if (!value) return '—';

    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return value;

    return new Intl.DateTimeFormat('es-MX', {
      day: '2-digit',
      month: 'short',
      year: 'numeric',
    }).format(date);
  }

  backlogDeltaLabel(delta: number): string {
    if (delta > 0) return '+' + String(delta);
    return String(delta);
  }

  backlogDeltaClass(delta: number): string {
    if (delta < 0) return 'delta--good';
    if (delta > 0) return 'delta--bad';
    return 'delta--neutral';
  }

  trackWeek(_: number, week: MaintenanceDashboardWeek): string {
    return week.week_start;
  }

  trackTicket(
    _: number,
    ticket: MaintenanceDashboardDrilldownTicket,
  ): number {
    return ticket.id;
  }

  private formatDateOnly(value: string): string {
    const [year, month, day] = value.split('-').map(Number);
    const date = new Date(year, month - 1, day, 12, 0, 0);

    return new Intl.DateTimeFormat('es-MX', {
      day: '2-digit',
      month: 'short',
    }).format(date);
  }
}
