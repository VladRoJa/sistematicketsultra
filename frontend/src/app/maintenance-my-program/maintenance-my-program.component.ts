import { CommonModule } from '@angular/common';
import { Component, OnInit, inject } from '@angular/core';
import { FormsModule } from '@angular/forms';

import {
  MaintenanceChecklistItem,
  MaintenanceMyProgram,
  MaintenanceMyProgramItem,
  MaintenancePreventiveService,
  MaintenanceWorkDetail,
} from '../services/maintenance-preventive.service';

type ProgramView = 'today' | 'week' | 'overdue' | 'pending';
type WorkSavingStep = 'bitacora' | 'evidence' | 'complete' | null;
type FoundState = '' | 'BUENO' | 'REQUIERE_ATENCION' | 'FUERA_SERVICIO';

@Component({
  selector: 'app-maintenance-my-program',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './maintenance-my-program.component.html',
  styleUrls: ['./maintenance-my-program.component.css'],
})
export class MaintenanceMyProgramComponent implements OnInit {
  private readonly service = inject(MaintenancePreventiveService);

  program: MaintenanceMyProgram | null = null;
  activeView: ProgramView = 'today';
  loading = false;
  errorMessage = '';

  expandedTicketId: number | null = null;
  workDetail: MaintenanceWorkDetail | null = null;
  workLoading = false;
  workSavingStep: WorkSavingStep = null;
  workErrorMessage = '';
  workSuccessMessage = '';

  estadoEncontrado: FoundState = '';
  notas = '';
  hallazgoDetectado = false;
  hallazgoDescripcion = '';
  generarCorrectivo = false;
  criticidadCorrectivo = 2;
  checkValues: Record<string, string> = {};

  evidenceFile: File | null = null;
  bitacoraSaved = false;
  evidenceSaved = false;
  derivedCorrectiveId: number | null = null;

  readonly foundStateOptions = [
    { value: 'BUENO' as const, label: 'Bueno' },
    {
      value: 'REQUIERE_ATENCION' as const,
      label: 'Requiere atención',
    },
    {
      value: 'FUERA_SERVICIO' as const,
      label: 'Fuera de servicio',
    },
  ];

  readonly checkOptions = [
    { value: 'OK', label: 'OK' },
    { value: 'ATENCION', label: 'Atención' },
    { value: 'NO_APLICA', label: 'N/A' },
  ];

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

  get checklistItems(): MaintenanceChecklistItem[] {
    return this.workDetail?.checklist?.items || [];
  }

  get hasChecklist(): boolean {
    return this.checklistItems.length > 0;
  }

  get canSaveBitacora(): boolean {
    if (
      this.workSavingStep !== null
      || this.bitacoraSaved
      || !this.estadoEncontrado
      || !this.notas.trim()
    ) {
      return false;
    }

    if (this.hallazgoDetectado && !this.hallazgoDescripcion.trim()) {
      return false;
    }

    return this.requiredChecksComplete();
  }

  get canUploadEvidence(): boolean {
    return Boolean(
      this.bitacoraSaved
      && !this.evidenceSaved
      && this.evidenceFile
      && this.workSavingStep === null,
    );
  }

  get canCompleteWork(): boolean {
    return Boolean(
      this.bitacoraSaved
      && this.evidenceSaved
      && this.workSavingStep === null,
    );
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
    this.closeWork();
  }

  isSelected(view: ProgramView): boolean {
    return this.activeView === view;
  }

  isWorkExpanded(item: MaintenanceMyProgramItem): boolean {
    return this.expandedTicketId === item.ticket_id;
  }

  canOpenWork(item: MaintenanceMyProgramItem): boolean {
    return (
      item.tipo_mantenimiento === 'PREVENTIVO'
      && item.operational_status !== 'PENDIENTE_VALIDACION'
    );
  }

  toggleWork(item: MaintenanceMyProgramItem): void {
    if (!this.canOpenWork(item)) {
      return;
    }

    if (this.expandedTicketId === item.ticket_id) {
      this.closeWork();
      return;
    }

    this.expandedTicketId = item.ticket_id;
    this.loadWorkDetail(item.ticket_id);
  }

  closeWork(): void {
    this.expandedTicketId = null;
    this.workDetail = null;
    this.workLoading = false;
    this.resetWorkForm();
  }

  loadWorkDetail(ticketId: number): void {
    this.workLoading = true;
    this.workErrorMessage = '';
    this.workSuccessMessage = '';
    this.workDetail = null;

    this.service.getWorkDetail(ticketId).subscribe({
      next: (detail) => {
        this.workDetail = detail;
        this.workLoading = false;
        this.hydrateWorkForm(detail);
      },
      error: (error) => {
        this.workLoading = false;
        this.workErrorMessage =
          error?.error?.mensaje
          || error?.error?.detail
          || 'No se pudo cargar el preventivo.';
      },
    });
  }

  setCheckValue(itemKey: string, value: string): void {
    this.checkValues = {
      ...this.checkValues,
      [itemKey]: value,
    };
  }

  getCheckValue(itemKey: string): string {
    return this.checkValues[itemKey] || '';
  }

  onHallazgoChanged(): void {
    if (!this.hallazgoDetectado) {
      this.hallazgoDescripcion = '';
      this.generarCorrectivo = false;
      this.criticidadCorrectivo = 2;
    }
  }

  saveBitacora(): void {
    if (
      !this.expandedTicketId
      || !this.canSaveBitacora
      || !this.estadoEncontrado
    ) {
      return;
    }

    this.workSavingStep = 'bitacora';
    this.workErrorMessage = '';
    this.workSuccessMessage = '';

    this.service.createWorkBitacora(
      this.expandedTicketId,
      {
        estado_encontrado: this.estadoEncontrado,
        notas: this.notas.trim(),
        checks: { ...this.checkValues },
        hallazgo_detectado: this.hallazgoDetectado,
        hallazgo_descripcion:
          this.hallazgoDescripcion.trim() || null,
        generar_correctivo:
          this.hallazgoDetectado && this.generarCorrectivo,
        criticidad_correctivo:
          this.hallazgoDetectado && this.generarCorrectivo
            ? this.criticidadCorrectivo
            : undefined,
      },
    ).subscribe({
      next: (response) => {
        this.workSavingStep = null;
        this.bitacoraSaved = true;
        this.derivedCorrectiveId = response.correctivo_id;
        this.workSuccessMessage = response.correctivo_id
          ? 'Bitácora guardada y correctivo generado #'
            + String(response.correctivo_id)
            + '.'
          : 'Bitácora guardada.';
      },
      error: (error) => {
        this.workSavingStep = null;
        this.workErrorMessage =
          error?.error?.mensaje
          || error?.error?.detail
          || 'No se pudo guardar la bitácora.';
      },
    });
  }

  onEvidenceSelected(event: Event): void {
    const input = event.target as HTMLInputElement;
    this.evidenceFile = input.files?.[0] || null;
    this.workErrorMessage = '';
  }

  uploadEvidence(): void {
    if (
      !this.expandedTicketId
      || !this.evidenceFile
      || !this.canUploadEvidence
    ) {
      return;
    }

    this.workSavingStep = 'evidence';
    this.workErrorMessage = '';
    this.workSuccessMessage = '';

    this.service.uploadWorkEvidence(
      this.expandedTicketId,
      this.evidenceFile,
    ).subscribe({
      next: () => {
        this.workSavingStep = null;
        this.evidenceSaved = true;
        this.evidenceFile = null;
        this.workSuccessMessage = 'Evidencia guardada.';
      },
      error: (error) => {
        this.workSavingStep = null;
        this.workErrorMessage =
          error?.error?.mensaje
          || error?.error?.detail
          || 'No se pudo subir la evidencia.';
      },
    });
  }

  completeWork(): void {
    if (!this.expandedTicketId || !this.canCompleteWork) {
      return;
    }

    const ticketId = this.expandedTicketId;
    this.workSavingStep = 'complete';
    this.workErrorMessage = '';
    this.workSuccessMessage = '';

    this.service.completeWork(ticketId).subscribe({
      next: () => {
        this.workSavingStep = null;
        this.closeWork();
        this.loadProgram();
      },
      error: (error) => {
        this.workSavingStep = null;
        this.workErrorMessage =
          error?.error?.mensaje
          || error?.error?.detail
          || 'No se pudo marcar el preventivo como realizado.';
      },
    });
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

  trackChecklistItem(_: number, item: MaintenanceChecklistItem): number {
    return item.id;
  }

  private requiredChecksComplete(): boolean {
    return this.checklistItems.every((item) => {
      if (!item.requerido) return true;
      return Boolean(this.checkValues[item.item_key]);
    });
  }

  private hydrateWorkForm(detail: MaintenanceWorkDetail): void {
    this.resetWorkForm();

    const latest = detail.bitacoras[0];
    if (latest) {
      this.bitacoraSaved = true;
      this.estadoEncontrado =
        (latest.estado_encontrado || '') as FoundState;
      this.notas = latest.notas || '';
      this.hallazgoDetectado = latest.hallazgo_detectado;
      this.hallazgoDescripcion =
        latest.hallazgo_descripcion || '';
      this.checkValues = { ...(latest.checks || {}) };
    }

    this.evidenceSaved = Boolean(detail.has_evidence);
  }

  private resetWorkForm(): void {
    this.workErrorMessage = '';
    this.workSuccessMessage = '';
    this.workSavingStep = null;
    this.estadoEncontrado = '';
    this.notas = '';
    this.hallazgoDetectado = false;
    this.hallazgoDescripcion = '';
    this.generarCorrectivo = false;
    this.criticidadCorrectivo = 2;
    this.checkValues = {};
    this.evidenceFile = null;
    this.bitacoraSaved = false;
    this.evidenceSaved = false;
    this.derivedCorrectiveId = null;
  }
}
