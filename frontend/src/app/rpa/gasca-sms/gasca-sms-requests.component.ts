import { CommonModule } from '@angular/common';
import { Component, OnDestroy, OnInit } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { Subscription, timer } from 'rxjs';
import { finalize } from 'rxjs/operators';

import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatSelectModule } from '@angular/material/select';
import { MatTableModule } from '@angular/material/table';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';

import {
  CreateGascaSmsRequestPayload,
  GascaSmsMotivo,
  GascaSmsRequest,
  GascaSmsRequestsListParams,
  GascaSmsRequestStatus,
  RpaGascaSmsService,
} from '../../services/rpa-gasca-sms.service';

interface MotivoOption {
  value: GascaSmsMotivo;
  label: string;
}

type GascaSmsDatePreset =
  | 'today'
  | 'yesterday'
  | 'last_7_days'
  | 'month'
  | 'custom'
  | 'all';

interface GascaSmsListFilterState {
  date_preset: GascaSmsDatePreset;
  date_from: string;
  date_to: string;
  status: string;
  pin: string;
  gasca_sucursal: string;
}

@Component({
  selector: 'app-gasca-sms-requests',
  standalone: true,
  templateUrl: './gasca-sms-requests.component.html',
  styleUrls: ['./gasca-sms-requests.component.css'],
  imports: [
    CommonModule,
    ReactiveFormsModule,
    MatButtonModule,
    MatCardModule,
    MatFormFieldModule,
    MatInputModule,
    MatSelectModule,
    MatTableModule,
    MatIconModule,
    MatProgressSpinnerModule,
    MatSnackBarModule,
  ],
})
export class GascaSmsRequestsComponent implements OnDestroy, OnInit {
  readonly displayedColumns = [
    'created_at',
    'pin',
    'telefono',
    'motivo',
    'status',
    'mensaje',
    'gasca',
  ];

  readonly motivoOptions: MotivoOption[] = [
    { value: 'HUELLA_NO_LEIDA', label: 'Huella no leída' },
    { value: 'VISITA_PROSPECTO', label: 'Visita / prospecto' },
    { value: 'SMS_NO_LLEGA', label: 'SMS no llega' },
    { value: 'OTRO', label: 'Otro' },
  ];

  readonly datePresetOptions: Array<{ value: GascaSmsDatePreset; label: string }> = [
    { value: 'today', label: 'Hoy' },
    { value: 'yesterday', label: 'Ayer' },
    { value: 'last_7_days', label: 'Últimos 7 días' },
    { value: 'month', label: 'Este mes' },
    { value: 'custom', label: 'Personalizado' },
    { value: 'all', label: 'Todo' },
  ];

  readonly statusOptions: Array<{ value: string; label: string }> = [
    { value: 'ALL', label: 'Todos' },
    { value: 'sent', label: 'SMS enviado' },
    { value: 'code_already_used', label: 'Código utilizado' },
    { value: 'code_not_found', label: 'Código no encontrado' },
    { value: 'phone_not_found_for_pin', label: 'Teléfono no coincide' },
    { value: 'code_not_generated_today', label: 'Código no es de hoy' },
    { value: 'failed', label: 'Error' },
  ];

  form = this.fb.group({
    pin: ['', [Validators.required, Validators.pattern(/^\d{1,5}$/)]],
    telefono: ['', [Validators.required, Validators.minLength(8), Validators.maxLength(24)]],
    motivo: ['SMS_NO_LLEGA', [Validators.required]],
    motivo_detalle: [''],
  });

  loadingCatalogs = false;
  creating = false;
  loadingList = false;
  autoRefreshingList = false;
  exportingList = false;

  latestResult: GascaSmsRequest | null = null;
  resultModalOpen = false;
  items: GascaSmsRequest[] = [];
  private autoRefreshSubscription: Subscription | null = null;

  listFilters: GascaSmsListFilterState = {
    date_preset: 'today',
    date_from: '',
    date_to: '',
    status: 'ALL',
    pin: '',
    gasca_sucursal: '',
  };

  listPage = 1;
  listPageSize = 25;
  listTotal = 0;
  listTotalPages = 0;
  listHasNext = false;
  listHasPrev = false;

  globalAccess = false;
  allowedSucursalesIds: number[] | null = null;

  constructor(
    private fb: FormBuilder,
    private gascaSmsService: RpaGascaSmsService,
    private snackBar: MatSnackBar,
  ) {}

  ngOnInit(): void {
    this.loadCatalogs();
    this.loadRecentRequests();
    this.startAutoRefresh();
  }

  ngOnDestroy(): void {
    this.autoRefreshSubscription?.unsubscribe();
  }

  private startAutoRefresh(): void {
    this.autoRefreshSubscription = timer(5000, 5000).subscribe(() => {
      if (this.creating || this.loadingList || this.autoRefreshingList || !this.hasLiveRequests()) {
        return;
      }

      this.loadRequests(this.listPage, { silent: true });
    });
  }

  private hasLiveRequests(): boolean {
    return this.items.some((item) => this.isLiveStatus(item.status));
  }

  private isLiveStatus(status?: string | null): boolean {
    const value = String(status || '').trim();

    return [
      'pending',
      'gasca_searching',
      'ready_to_send',
      'multiple_candidates_selected_latest',
      'sms_sending',
    ].includes(value);
  }

  loadCatalogs(): void {
    this.loadingCatalogs = true;

    this.gascaSmsService.getCatalogs()
      .pipe(finalize(() => this.loadingCatalogs = false))
      .subscribe({
        next: (response) => {
          this.globalAccess = response.global_access;
          this.allowedSucursalesIds = response.allowed_sucursales_ids;
        },
        error: () => {
          this.showSnack('No se pudieron cargar permisos/catálogos del módulo.');
        },
      });
  }

  loadRecentRequests(): void {
    this.loadRequests(1);
  }

  loadRequests(page: number = this.listPage, options: { silent?: boolean } = {}): void {
    if (options.silent) {
      this.autoRefreshingList = true;
    } else {
      this.loadingList = true;
    }

    this.listPage = Math.max(1, page);

    const params = this.buildListParams();

    this.gascaSmsService.listRequests(params)
      .pipe(finalize(() => {
        if (options.silent) {
          this.autoRefreshingList = false;
        } else {
          this.loadingList = false;
        }
      }))
      .subscribe({
        next: (response) => {
          this.items = response.items || [];

          if (this.latestResult) {
            const freshResult = this.items.find((item) => item.id === this.latestResult?.id);

            if (freshResult) {
              this.latestResult = freshResult;
            }
          }

          this.listPage = response.page || this.listPage;
          this.listPageSize = response.page_size || this.listPageSize;
          this.listTotal = response.total || 0;
          this.listTotalPages = response.total_pages || 0;
          this.listHasNext = !!response.has_next;
          this.listHasPrev = !!response.has_prev;
        },
        error: () => {
          this.items = [];
          this.listTotal = 0;
          this.listTotalPages = 0;
          this.listHasNext = false;
          this.listHasPrev = false;
          this.showSnack('No se pudo cargar el historial filtrado.');
        },
      });
  }

  exportFilteredRequests(): void {
    if (this.exportingList) {
      return;
    }

    this.exportingList = true;

    this.gascaSmsService.exportRequests(this.buildListParams())
      .pipe(finalize(() => this.exportingList = false))
      .subscribe({
        next: (blob) => {
          this.downloadBlob(blob, this.buildExportFilename());
        },
        error: () => {
          this.showSnack('No se pudo exportar el historial filtrado.');
        },
      });
  }

  private downloadBlob(blob: Blob, filename: string): void {
    const objectUrl = window.URL.createObjectURL(blob);
    const anchor = document.createElement('a');

    anchor.href = objectUrl;
    anchor.download = filename;
    anchor.click();

    window.URL.revokeObjectURL(objectUrl);
  }

  private buildExportFilename(): string {
    const now = new Date();
    const stamp = now.toISOString().slice(0, 19).replace(/[-:T]/g, '');
    const preset = this.listFilters.date_preset || 'export';

    return `gasca_sms_${preset}_${stamp}.csv`;
  }

  private buildListParams(): GascaSmsRequestsListParams {
    return {
      page: this.listPage,
      page_size: this.listPageSize,
      date_preset: this.listFilters.date_preset,
      date_from: this.listFilters.date_preset === 'custom'
        ? this.listFilters.date_from
        : '',
      date_to: this.listFilters.date_preset === 'custom'
        ? this.listFilters.date_to
        : '',
      status: this.listFilters.status,
      pin: this.listFilters.pin.trim(),
      gasca_sucursal: this.listFilters.gasca_sucursal.trim(),
    };
  }

  applyListFilters(): void {
    this.loadRequests(1);
  }

  clearListFilters(): void {
    this.listFilters = {
      date_preset: 'today',
      date_from: '',
      date_to: '',
      status: 'ALL',
      pin: '',
      gasca_sucursal: '',
    };

    this.loadRequests(1);
  }

  goToPreviousListPage(): void {
    if (!this.listHasPrev || this.loadingList) {
      return;
    }

    this.loadRequests(this.listPage - 1);
  }

  goToNextListPage(): void {
    if (!this.listHasNext || this.loadingList) {
      return;
    }

    this.loadRequests(this.listPage + 1);
  }

  shouldShowCustomDateRange(): boolean {
    return this.listFilters.date_preset === 'custom';
  }

  getListSummary(): string {
    if (this.listTotal === 0) {
      return 'Sin solicitudes encontradas';
    }

    const visibleCount = this.items.length;
    const start = ((this.listPage - 1) * this.listPageSize) + 1;
    const end = start + visibleCount - 1;

    return `${start}-${end} de ${this.listTotal} solicitudes`;
  }

  setListDatePreset(value: string): void {
    this.listFilters.date_preset = value as GascaSmsDatePreset;

    if (this.listFilters.date_preset !== 'custom') {
      this.listFilters.date_from = '';
      this.listFilters.date_to = '';
    }
  }

  setListDateFrom(value: string): void {
    this.listFilters.date_from = value;
  }

  setListDateTo(value: string): void {
    this.listFilters.date_to = value;
  }

  setListStatus(value: string): void {
    this.listFilters.status = value;
  }

  setListPin(value: string): void {
    this.listFilters.pin = value;
  }

  setListGascaSucursal(value: string): void {
    this.listFilters.gasca_sucursal = value;
  }

  submit(): void {
    if (this.form.invalid || this.creating) {
      this.form.markAllAsTouched();
      return;
    }

    const payload: CreateGascaSmsRequestPayload = {
      pin: this.pinValue,
      telefono: this.telefonoValue,
      motivo: this.motivoValue,
      motivo_detalle: this.motivoDetalleValue || null,
    };

    this.creating = true;
    this.latestResult = null;

    this.gascaSmsService.createRequest(payload)
      .pipe(finalize(() => this.creating = false))
      .subscribe({
        next: (response) => {
          this.latestResult = response.request;
          this.resultModalOpen = true;
          this.loadRequests(1);
        },
        error: (error) => {
          const detail = error?.error?.detail || 'No se pudo crear la solicitud.';
          this.showSnack(detail);
        },
      });
  }

  clearForm(): void {
    this.form.reset({
      pin: '',
      telefono: '',
      motivo: 'SMS_NO_LLEGA',
      motivo_detalle: '',
    });
    this.latestResult = null;
    this.resultModalOpen = false;
  }

  closeResultModal(): void {
    this.resultModalOpen = false;
  }

  get pinValue(): string {
    return String(this.form.get('pin')?.value || '').trim();
  }

  get telefonoValue(): string {
    return String(this.form.get('telefono')?.value || '').trim();
  }

  get motivoValue(): GascaSmsMotivo {
    return String(this.form.get('motivo')?.value || 'SMS_NO_LLEGA') as GascaSmsMotivo;
  }

  get motivoDetalleValue(): string {
    return String(this.form.get('motivo_detalle')?.value || '').trim();
  }

  get pinError(): string {
    const control = this.form.get('pin');

    if (!control || !control.touched || !control.errors) {
      return '';
    }

    if (control.errors['required']) {
      return 'El PIN es obligatorio.';
    }

    if (control.errors['pattern']) {
      return 'Captura de 1 a 5 dígitos. Ejemplo: 8123 o 12879.';
    }

    return 'PIN inválido.';
  }

  get telefonoError(): string {
    const control = this.form.get('telefono');

    if (!control || !control.touched || !control.errors) {
      return '';
    }

    if (control.errors['required']) {
      return 'El teléfono es obligatorio.';
    }

    return 'Teléfono inválido.';
  }

  get latestResultIsSuccess(): boolean {
    return this.isSuccessStatus(this.latestResult?.status);
  }

  get latestResultIsBlocked(): boolean {
    return !!this.latestResult && !this.latestResultIsSuccess;
  }

  isSuccessStatus(status?: string | null): boolean {
    return status === 'sent' || status === 'ready_to_send' || status === 'multiple_candidates_selected_latest';
  }

  statusLabel(status?: string | null): string {
    const value = String(status || '').trim() as GascaSmsRequestStatus;

    const labels: Record<string, string> = {
      pending: 'Pendiente',
      gasca_searching: 'Buscando en Gasca',
      ready_to_send: 'Código vigente',
      multiple_candidates_selected_latest: 'Código vigente más reciente',
      sms_sending: 'Enviando SMS',
      sent: 'SMS enviado',
      code_not_found: 'Código no encontrado',
      phone_not_found_for_pin: 'Teléfono no coincide',
      code_not_generated_today: 'Código no es de hoy',
      code_already_used: 'Código utilizado',
      phone_required_for_contract: 'Teléfono requerido',
      manual_review: 'Revisión manual',
      failed: 'Error',
    };

    return labels[value] || value || 'Sin estado';
  }

  motivoLabel(motivo?: string | null): string {
    const found = this.motivoOptions.find((item) => item.value === motivo);
    return found?.label || motivo || 'Sin motivo';
  }

  formatDateTime(value?: string | null): string {
    if (!value) {
      return '—';
    }

    const date = new Date(value);

    if (Number.isNaN(date.getTime())) {
      return value;
    }

    return date.toLocaleString('es-MX', {
      dateStyle: 'short',
      timeStyle: 'short',
    });
  }

  rowStatusClass(item: GascaSmsRequest): string {
    if (this.isSuccessStatus(item.status)) {
      return 'status-success';
    }

    if (item.status === 'failed') {
      return 'status-error';
    }

    return 'status-blocked';
  }

  private showSnack(message: string): void {
    this.snackBar.open(message, 'Cerrar', {
      duration: 5000,
    });
  }
}
