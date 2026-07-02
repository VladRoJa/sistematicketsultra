import { CommonModule } from '@angular/common';
import { Component, OnInit } from '@angular/core';
import { FormsModule } from '@angular/forms';

import { AuthService } from '../../services/auth.service';
import {
  TrackGenerationMode,
  TrackService,
  TrackVentaTotalForecastResponse,
  TrackVentaTotalForecastScope,
  TrackVentaTotalForecastSummary,
} from '../../services/track.service';

@Component({
  selector: 'app-track-forecast',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './track-forecast.component.html',
  styleUrls: ['./track-forecast.component.css'],
})
export class TrackForecastComponent implements OnInit {
  trackDate = this.getTodayIsoDate();
  generationMode: TrackGenerationMode = 'manual_preview';
  scope: TrackVentaTotalForecastScope = 'national';
  branch = '';

  loading = false;
  errorMessage = '';
  forecast: TrackVentaTotalForecastResponse | null = null;

  private readonly betaUserId = 47;

  constructor(
    private readonly trackService: TrackService,
    private readonly authService: AuthService,
  ) {}

  ngOnInit(): void {
    if (!this.puedeVerForecastBeta()) {
      this.errorMessage = 'No tienes acceso beta a Proyección y Metas.';
      return;
    }

    this.cargarForecast();
  }

  puedeVerForecastBeta(): boolean {
    const user = this.authService.getUser() as any;
    const userId = Number(user?.id ?? user?.user_id ?? user?.usuario_id ?? 0);

    return userId === this.betaUserId;
  }

  cargarForecast(): void {
    if (!this.puedeVerForecastBeta()) {
      this.errorMessage = 'No tienes acceso beta a Proyección y Metas.';
      return;
    }

    this.loading = true;
    this.errorMessage = '';
    this.forecast = null;

    this.trackService
      .getVentaTotalForecast(
        this.trackDate,
        this.generationMode,
        this.scope,
        this.branch,
      )
      .subscribe({
        next: (response) => {
          this.loading = false;

          if (response.status !== 'ok') {
            this.errorMessage = response.message || response.detail || 'No fue posible cargar la proyección.';
            return;
          }

          this.forecast = response;
        },
        error: (error) => {
          this.loading = false;
          this.errorMessage =
            error?.error?.message ||
            error?.error?.detail ||
            'No fue posible cargar la proyección.';
        },
      });
  }

  get summary(): TrackVentaTotalForecastSummary | null {
    return this.forecast?.summary ?? null;
  }

  get goalStatusMessage(): string {
    return this.forecast?.data_quality?.goal_status_message || '';
  }

  get historyConfidence(): string {
    return this.forecast?.historical_curve?.confidence || 'sin dato';
  }

  get historyCoverageLabel(): string {
    const coverage = this.forecast?.data_quality?.history_coverage;

    if (!coverage) {
      return 'Sin cobertura histórica';
    }

    return `${coverage.months_count} meses (${coverage.first_month || '—'} a ${coverage.last_month || '—'})`;
  }

  get resolvedVersionLabel(): string {
    const version = this.forecast?.metadata?.resolved_version;

    if (!version) {
      return 'Sin versión resuelta';
    }

    return `Versión ${version.id} · ${version.version_type} · ${version.status}`;
  }

  formatCurrency(value: number | null | undefined): string {
    if (value === null || value === undefined) {
      return '—';
    }

    return new Intl.NumberFormat('es-MX', {
      style: 'currency',
      currency: 'MXN',
      maximumFractionDigits: 0,
    }).format(value);
  }

  formatPercent(value: number | null | undefined): string {
    if (value === null || value === undefined) {
      return '—';
    }

    return new Intl.NumberFormat('es-MX', {
      style: 'percent',
      minimumFractionDigits: 1,
      maximumFractionDigits: 1,
    }).format(value);
  }

  formatNumber(value: number | null | undefined): string {
    if (value === null || value === undefined) {
      return '—';
    }

    return new Intl.NumberFormat('es-MX', {
      maximumFractionDigits: 2,
    }).format(value);
  }

  private getTodayIsoDate(): string {
    const now = new Date();
    now.setMinutes(now.getMinutes() - now.getTimezoneOffset());

    return now.toISOString().slice(0, 10);
  }
}
