// frontend/src/app/openings/pages/openings-list/openings-list.component.ts


import { CommonModule } from '@angular/common';
import { Component, OnInit } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Router } from '@angular/router';

import {
  Opening,
  OpeningCreatePayload,
  OpeningStatus,
  SucursalOption,
} from '../../models/opening.model';
import { OpeningsService } from '../../services/openings.service';

@Component({
  selector: 'app-openings-list',
  standalone: true,
  imports: [
    CommonModule,
    FormsModule,
  ],
  templateUrl: './openings-list.component.html',
  styleUrls: ['./openings-list.component.css'],
})
export class OpeningsListComponent implements OnInit {
  loading = false;
  saving = false;
  errorMessage = '';
  successMessage = '';

  openings: Opening[] = [];
  sucursales: SucursalOption[] = [];

  total = 0;
  page = 1;
  pageSize = 25;
  totalPages = 0;
  hasNext = false;
  hasPrev = false;

  isCreatePanelOpen = false;

  filters = {
    q: '',
    status: 'ALL' as OpeningStatus | 'ALL',
    page: 1,
    page_size: 25,
  };

  form = {
    sucursal_id: null as number | null,
    opening_key: '',
    name: '',
    description: '',
    status: 'PLANEADA' as OpeningStatus,
    planned_start_date: '',
    target_opening_date: '',
    budget_authorized_total: null as number | null,
    budget_currency_code: 'MXN',
  };

  readonly statusOptions: Array<OpeningStatus | 'ALL'> = [
    'ALL',
    'BORRADOR',
    'PLANEADA',
    'EN_EJECUCION',
    'EN_RIESGO',
    'PAUSADA',
    'ABIERTA',
    'CANCELADA',
    'CERRADA',
  ];

  readonly createStatusOptions: OpeningStatus[] = [
    'BORRADOR',
    'PLANEADA',
    'EN_EJECUCION',
    'EN_RIESGO',
  ];

  constructor(
    private openingsService: OpeningsService,
    private router: Router,
  ) {}

  ngOnInit(): void {
    this.loadInitialData();
  }

  loadInitialData(): void {
    this.loadSucursales();
    this.loadOpenings();
  }

  loadSucursales(): void {
    this.openingsService.listSucursales().subscribe({
      next: (rows) => {
        this.sucursales = rows || [];
      },
      error: () => {
        this.sucursales = [];
      },
    });
  }

  loadOpenings(): void {
    this.loading = true;
    this.clearMessages();

    this.openingsService.listOpenings(this.filters).subscribe({
      next: (response) => {
        this.openings = response.items || [];
        this.page = response.page;
        this.pageSize = response.page_size;
        this.total = response.total;
        this.totalPages = response.total_pages;
        this.hasNext = response.has_next;
        this.hasPrev = response.has_prev;
        this.loading = false;
      },
      error: (error) => {
        this.loading = false;
        this.errorMessage = this.resolveErrorMessage(
          error,
          'No se pudieron cargar las aperturas.',
        );
      },
    });
  }

  applyFilters(): void {
    this.filters.page = 1;
    this.loadOpenings();
  }

  clearFilters(): void {
    this.filters = {
      q: '',
      status: 'ALL',
      page: 1,
      page_size: 25,
    };

    this.loadOpenings();
  }

  goToPreviousPage(): void {
    if (!this.hasPrev) {
      return;
    }

    this.filters.page = Math.max((this.filters.page || 1) - 1, 1);
    this.loadOpenings();
  }

  goToNextPage(): void {
    if (!this.hasNext) {
      return;
    }

    this.filters.page = (this.filters.page || 1) + 1;
    this.loadOpenings();
  }

  toggleCreatePanel(): void {
    this.isCreatePanelOpen = !this.isCreatePanelOpen;
  }

  closeCreatePanel(): void {
    this.isCreatePanelOpen = false;
  }

  getCreatePanelButtonLabel(): string {
    return this.isCreatePanelOpen ? 'Cerrar alta' : 'Nueva apertura';
  }

  canCreateOpening(): boolean {
    return Boolean(
      this.form.sucursal_id &&
      this.form.opening_key.trim() &&
      this.form.name.trim() &&
      !this.saving,
    );
  }

  createOpening(): void {
    if (!this.canCreateOpening()) {
      this.errorMessage = 'Completa sucursal, clave y nombre de la apertura.';
      return;
    }

    const payload: OpeningCreatePayload = {
      sucursal_id: this.form.sucursal_id,
      opening_key: this.form.opening_key.trim().toUpperCase(),
      name: this.form.name.trim(),
      description: this.form.description.trim() || null,
      status: this.form.status,
      planned_start_date: this.form.planned_start_date || null,
      target_opening_date: this.form.target_opening_date || null,
      budget_authorized_total: this.form.budget_authorized_total,
      budget_currency_code: this.form.budget_currency_code || 'MXN',
    };

    this.saving = true;
    this.clearMessages();

    this.openingsService.createOpening(payload).subscribe({
      next: (response) => {
        this.saving = false;
        this.successMessage = response.message || 'Apertura creada.';
        this.resetCreateForm();
        this.closeCreatePanel();
        this.loadOpenings();

        if (response.item?.id) {
          this.goToOpening(response.item);
        }
      },
      error: (error) => {
        this.saving = false;
        this.errorMessage = this.resolveErrorMessage(
          error,
          'No se pudo crear la apertura.',
        );
      },
    });
  }

  goToOpening(opening: Opening): void {
    this.router.navigate(['/aperturas', opening.id]);
  }

  getTotalInProgress(): number {
    return this.openings.filter((opening) =>
      ['PLANEADA', 'EN_EJECUCION', 'EN_RIESGO'].includes(opening.status),
    ).length;
  }

  getTotalAtRisk(): number {
    return this.openings.filter((opening) => opening.status === 'EN_RIESGO').length;
  }

  getTotalOpened(): number {
    return this.openings.filter((opening) => opening.status === 'ABIERTA').length;
  }

  getTotalBudget(): number {
    return this.openings.reduce((total, opening) => {
      return total + Number(opening.budget_authorized_total || 0);
    }, 0);
  }

  getStatusLabel(status: string | null | undefined): string {
    const labels: Record<string, string> = {
      ALL: 'Todas',
      BORRADOR: 'Borrador',
      PLANEADA: 'Planeada',
      EN_EJECUCION: 'En ejecución',
      EN_RIESGO: 'En riesgo',
      PAUSADA: 'Pausada',
      ABIERTA: 'Abierta',
      CANCELADA: 'Cancelada',
      CERRADA: 'Cerrada',
    };

    return labels[String(status || '')] || String(status || 'Sin estado');
  }

  getOpeningStatusTone(opening: Opening): string {
    const tones: Record<string, string> = {
      BORRADOR: 'draft',
      PLANEADA: 'planned',
      EN_EJECUCION: 'progress',
      EN_RIESGO: 'risk',
      PAUSADA: 'paused',
      ABIERTA: 'opened',
      CANCELADA: 'cancelled',
      CERRADA: 'closed',
    };

    return tones[opening.status] || 'draft';
  }

  getDaysRemaining(opening: Opening): number | null {
    if (!opening.target_opening_date) {
      return null;
    }

    const today = new Date();
    const target = new Date(`${opening.target_opening_date}T00:00:00`);
    const todayStart = new Date(today.getFullYear(), today.getMonth(), today.getDate());
    const diffMs = target.getTime() - todayStart.getTime();

    return Math.ceil(diffMs / (1000 * 60 * 60 * 24));
  }

  getDaysRemainingLabel(opening: Opening): string {
    const days = this.getDaysRemaining(opening);

    if (days === null) {
      return 'Sin fecha objetivo';
    }

    if (days < 0) {
      return `${Math.abs(days)} días de atraso`;
    }

    if (days === 0) {
      return 'Apertura hoy';
    }

    return `${days} días restantes`;
  }

  getDaysRemainingTone(opening: Opening): string {
    const days = this.getDaysRemaining(opening);

    if (days === null) {
      return 'neutral';
    }

    if (days < 0) {
      return 'danger';
    }

    if (days <= 7) {
      return 'warning';
    }

    return 'success';
  }

  getSucursalName(opening: Opening): string {
    return opening.sucursal?.sucursal || `Sucursal ${opening.sucursal_id}`;
  }

  getDateLabel(value: string | null | undefined, emptyLabel = 'Sin fecha'): string {
    if (!value) {
      return emptyLabel;
    }

    const date = new Date(`${value}T00:00:00`);

    if (Number.isNaN(date.getTime())) {
      return value;
    }

    return new Intl.DateTimeFormat('es-MX', {
      dateStyle: 'medium',
      timeZone: 'America/Tijuana',
    }).format(date);
  }

  getMoneyLabel(value: number | null | undefined, currency = 'MXN'): string {
    const amount = Number(value || 0);

    return new Intl.NumberFormat('es-MX', {
      style: 'currency',
      currency: currency || 'MXN',
      maximumFractionDigits: 0,
    }).format(amount);
  }

  getOpeningInitial(opening: Opening): string {
    const source = opening.opening_key || opening.name || 'A';

    return source.trim().charAt(0).toUpperCase() || 'A';
  }

  getOpeningSubtitle(opening: Opening): string {
    const municipio = opening.sucursal?.municipio;
    const estado = opening.sucursal?.estado;

    return [municipio, estado].filter(Boolean).join(', ') || this.getSucursalName(opening);
  }

  trackByOpeningId(_index: number, opening: Opening): number {
    return opening.id;
  }

  private resetCreateForm(): void {
    this.form = {
      sucursal_id: null,
      opening_key: '',
      name: '',
      description: '',
      status: 'PLANEADA',
      planned_start_date: '',
      target_opening_date: '',
      budget_authorized_total: null,
      budget_currency_code: 'MXN',
    };
  }

  private clearMessages(): void {
    this.errorMessage = '';
    this.successMessage = '';
  }

  private resolveErrorMessage(error: unknown, fallback: string): string {
    const response = error as {
      error?: {
        detail?: string;
        message?: string;
        errors?: string[];
      };
      message?: string;
    };

    if (response?.error?.errors?.length) {
      return response.error.errors.join(' ');
    }

    return response?.error?.detail ||
      response?.error?.message ||
      response?.message ||
      fallback;
  }
}