import { CommonModule } from '@angular/common';
import { Component, OnInit } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
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
  GascaSmsRequestStatus,
  RpaGascaSmsService,
} from '../../services/rpa-gasca-sms.service';

interface MotivoOption {
  value: GascaSmsMotivo;
  label: string;
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
export class GascaSmsRequestsComponent implements OnInit {
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

  form = this.fb.group({
    pin: ['', [Validators.required, Validators.pattern(/^\d{1,5}$/)]],
    telefono: ['', [Validators.required, Validators.minLength(8), Validators.maxLength(24)]],
    motivo: ['SMS_NO_LLEGA', [Validators.required]],
    motivo_detalle: [''],
  });

  loadingCatalogs = false;
  creating = false;
  loadingList = false;

  latestResult: GascaSmsRequest | null = null;
  items: GascaSmsRequest[] = [];

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
    this.loadingList = true;

    this.gascaSmsService.listRequests({ limit: 10 })
      .pipe(finalize(() => this.loadingList = false))
      .subscribe({
        next: (response) => {
          this.items = response.items || [];
        },
        error: () => {
          this.showSnack('No se pudo cargar el historial reciente.');
        },
      });
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
          this.showSnack(response.message || 'Solicitud procesada.');
          this.loadRecentRequests();
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
