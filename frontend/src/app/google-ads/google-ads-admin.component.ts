import { CommonModule } from '@angular/common';
import { Component, OnDestroy, OnInit } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { HttpErrorResponse } from '@angular/common/http';
import { Subject, takeUntil } from 'rxjs';

import {
  GoogleAdsAccountCheck,
  GoogleAdsAdminService,
  GoogleAdsCampaignDaily,
  GoogleAdsOAuthStatus
} from './google-ads-admin.service';

function dateInputValue(date: Date): string {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
}

@Component({
  selector: 'app-google-ads-admin',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './google-ads-admin.component.html',
  styleUrls: ['./google-ads-admin.component.css']
})
export class GoogleAdsAdminComponent implements OnInit, OnDestroy {
  private readonly destroy$ = new Subject<void>();

  status: GoogleAdsOAuthStatus | null = null;
  accountCheck: GoogleAdsAccountCheck | null = null;
  report: GoogleAdsCampaignDaily | null = null;

  loadingStatus = false;
  connecting = false;
  checkingAccount = false;
  loadingReport = false;

  statusError = '';
  connectError = '';
  accountError = '';
  reportError = '';

  dateTo = dateInputValue(new Date());
  dateFrom = dateInputValue(new Date(Date.now() - 6 * 24 * 60 * 60 * 1000));

  constructor(private readonly googleAds: GoogleAdsAdminService) {}

  ngOnInit(): void {
    this.reloadStatus();
  }

  ngOnDestroy(): void {
    this.destroy$.next();
    this.destroy$.complete();
  }

  get isAuthorized(): boolean {
    return this.status?.enabled === true && this.status.authorized === true;
  }

  get isAccountVerified(): boolean {
    return this.accountCheck?.account_access_verified === true;
  }

  get isReportDisabled(): boolean {
    return !this.isAccountVerified || this.loadingReport || this.checkingAccount;
  }

  get canCheckAccount(): boolean {
    return this.isAuthorized && !this.checkingAccount && !this.connecting;
  }

  get connectionLabel(): string {
    if (this.loadingStatus) return 'Consultando';
    if (this.status?.enabled !== true) return 'OAuth no configurado';
    return this.status.authorized ? 'Autorización guardada' : 'Sin autorización';
  }

  get reportRowCount(): number {
    return this.report?.rows.length ?? 0;
  }

  reloadStatus(): void {
    if (this.loadingStatus) return;
    this.loadingStatus = true;
    this.statusError = '';
    this.accountError = '';
    this.reportError = '';
    this.accountCheck = null;
    this.report = null;

    this.googleAds.getStatus()
      .pipe(takeUntil(this.destroy$))
      .subscribe({
        next: (value) => {
          this.status = value;
          this.loadingStatus = false;
        },
        error: (error: HttpErrorResponse) => {
          this.status = null;
          this.loadingStatus = false;
          this.statusError = this.errorText(error);
        }
      });
  }

  connect(): void {
    if (this.connecting || this.status?.enabled !== true) return;
    this.connecting = true;
    this.connectError = '';

    this.googleAds.startAuthorization()
      .pipe(takeUntil(this.destroy$))
      .subscribe({
        next: (result) => {
          this.connecting = false;
          // Google is opened in the SAME tab and browser where M1 set the cookie.
          // Do not send an OAuth code or refresh token through Angular.
          try {
            const url = new URL(result.authorization_url);
            if (
              url.protocol !== 'https:' ||
              url.hostname !== 'accounts.google.com' ||
              url.pathname !== '/o/oauth2/v2/auth'
            ) {
              this.connectError = 'La URL de autorización recibida no es válida.';
              return;
            }
            window.location.assign(url.href);
          } catch {
            this.connectError = 'No se pudo abrir la autorización de Google.';
          }
        },
        error: (error: HttpErrorResponse) => {
          this.connecting = false;
          this.connectError = this.errorText(error);
        }
      });
  }

  verifyAccess(): void {
    if (!this.canCheckAccount) return;
    this.checkingAccount = true;
    this.accountError = '';
    this.reportError = '';
    this.accountCheck = null;
    this.report = null;

    this.googleAds.checkAccount()
      .pipe(takeUntil(this.destroy$))
      .subscribe({
        next: (value) => {
          this.checkingAccount = false;
          this.accountCheck = value;
        },
        error: (error: HttpErrorResponse) => {
          this.checkingAccount = false;
          this.accountError = this.errorText(error);
        }
      });
  }

  loadReport(): void {
    if (this.isReportDisabled) return;
    this.reportError = '';
    this.report = null;

    if (!this.isValidDateRange()) {
      this.reportError = 'Selecciona un rango válido de entre 1 y 31 días.';
      return;
    }
    this.loadingReport = true;
    this.googleAds.getCampaignDaily(this.dateFrom, this.dateTo)
      .pipe(takeUntil(this.destroy$))
      .subscribe({
        next: (value) => {
          this.loadingReport = false;
          this.report = value;
        },
        error: (error: HttpErrorResponse) => {
          this.loadingReport = false;
          this.reportError = this.errorText(error);
        }
      });
  }

  formatInteger(value: number): string {
    return new Intl.NumberFormat('es-MX', { maximumFractionDigits: 0 }).format(value);
  }

  formatCost(amount: string, currency: string): string {
    const n = Number(amount);
    if (!Number.isFinite(n)) return amount;
    try {
      return new Intl.NumberFormat('es-MX', {
        style: 'currency',
        currency: currency || 'MXN',
        minimumFractionDigits: 2,
        maximumFractionDigits: 2
      }).format(n);
    } catch {
      return `${amount} ${currency}`;
    }
  }

  formatDateTime(value: string | null | undefined): string {
    if (!value) return 'Sin registro';
    const parsed = new Date(value);
    return Number.isNaN(parsed.getTime())
      ? value
      : parsed.toLocaleString('es-MX');
  }

  private isValidDateRange(): boolean {
    if (!/^\d{4}-\d{2}-\d{2}$/.test(this.dateFrom) ||
        !/^\d{4}-\d{2}-\d{2}$/.test(this.dateTo)) return false;
    const from = new Date(this.dateFrom + 'T12:00:00');
    const to = new Date(this.dateTo + 'T12:00:00');
    const difference = Math.round((to.getTime() - from.getTime()) / 86400000);
    return Number.isFinite(difference) && difference >= 0 && difference < 31
      && dateInputValue(from) === this.dateFrom && dateInputValue(to) === this.dateTo;
  }

  private errorText(error: HttpErrorResponse): string {
    // Backend M1/M2 send stable error codes; never expose raw provider diagnostics.
    const code = error.error?.code as string | undefined;
    if (error.status === 401) return 'Tu sesión expiró. Inicia sesión nuevamente.';
    if (error.status === 403) return 'Tu usuario no tiene permiso de administrador.';
    const known: Record<string, string> = {
      GOOGLE_ADS_READONLY_DISABLED:
        'La consulta Google Ads todavía está deshabilitada en el servidor.',
      GOOGLE_ADS_OAUTH_DISABLED_OR_UNCONFIGURED:
        'La configuración privada de OAuth todavía no está habilitada.',
      GOOGLE_ADS_DEVELOPER_TOKEN_MISSING:
        'Falta configurar el developer token de Google Ads en el backend.',
      GOOGLE_ADS_NOT_CONNECTED:
        'Debes conectar Google Ads antes de verificar el acceso.',
      GOOGLE_ADS_CUSTOMER_BINDING_MISMATCH:
        'La cuenta configurada no coincide con la autorización guardada.',
      GOOGLE_ADS_REAUTHORIZATION_REQUIRED:
        'Google requiere una nueva autorización. Usa Conectar nuevamente.',
      GOOGLE_ADS_ACCOUNT_ACCESS_DENIED:
        'Google Ads rechazó el acceso. Revisa los permisos y el MCC.',
      GOOGLE_ADS_API_QUOTA_OR_RATE_LIMIT:
        'Google Ads alcanzó un límite de consultas. Intenta más tarde.',
      GOOGLE_ADS_TARGET_IS_MANAGER:
        'La cuenta seleccionada es un MCC. Se requiere una cuenta publicitaria cliente.',
      GOOGLE_ADS_DATE_RANGE_INVALID:
        'El intervalo solicitado es inválido (máximo 31 días).',
      GOOGLE_ADS_RESPONSE_TOO_LARGE:
        'Demasiadas filas. Selecciona un rango más corto.'
    };
    if (code && known[code]) return known[code];
    if (error.status === 503) return 'La integración no está disponible todavía.';
    return 'No se pudo completar la consulta. Intenta nuevamente.';
  }
}
