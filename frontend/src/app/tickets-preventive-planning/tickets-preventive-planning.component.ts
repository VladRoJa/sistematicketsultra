import { CommonModule } from '@angular/common';
import { Component, OnInit, inject } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatDialog, MatDialogModule } from '@angular/material/dialog';

import {
  MaintenancePreventiveService,
  PreventiveBatch,
  PreventiveBatchSummary,
  PreventiveBranch,
  PreventiveDraftItem,
  PreventiveEquipment,
  PreventivePlanningContext,
} from '../services/maintenance-preventive.service';
import { DialogoConfirmacionComponent } from '../shared/dialogo-confirmacion/dialogo-confirmacion.component';

interface PreventiveFamilyOption {
  id: number;
  key: string;
  nombre: string;
}

@Component({
  selector: 'app-tickets-preventive-planning',
  standalone: true,
  imports: [CommonModule, FormsModule, MatDialogModule],
  templateUrl: './tickets-preventive-planning.component.html',
  styleUrls: ['./tickets-preventive-planning.component.css'],
})
export class TicketsPreventivePlanningComponent implements OnInit {
  private readonly preventiveService = inject(MaintenancePreventiveService);
  private readonly dialog = inject(MatDialog);

  context: PreventivePlanningContext = {
    sucursales: [],
    responsables: [],
    building_classifications: [],
  };
  batches: PreventiveBatchSummary[] = [];
  selectedBatch: PreventiveBatch | null = null;
  equipment: PreventiveEquipment[] = [];

  loading = false;
  saving = false;
  errorMessage = '';
  successMessage = '';

  newBatchName = '';
  periodStart = '';
  periodEnd = '';

  targetType: 'EQUIPO' | 'EDIFICIO' = 'EQUIPO';
  branchId: number | null = null;
  familyId: number | null = null;
  buildingClassificationId: number | null = null;
  equipmentSearch = '';
  selectedEquipmentIds = new Set<number>();
  responsibleUsername = '';
  programmedDate = '';
  activity = '';
  observations = '';
  repeatEnabled = false;
  repeatIntervalWorkdays = 20;
  readonly repeatIntervalOptions = [5, 10, 15, 20, 30, 60, 90];

  importFile: File | null = null;

  ngOnInit(): void {
    this.loadInitialData();
  }

  get selectedBranch(): PreventiveBranch | null {
    return (
      this.context.sucursales.find(
        (branch) => branch.id === this.branchId,
      ) || null
    );
  }

  get isManualEquipment(): boolean {
    return this.targetType === 'EQUIPO';
  }

  get isManualBuilding(): boolean {
    return this.targetType === 'EDIFICIO';
  }

  get selectedBuildingClassification() {
    return (
      this.context.building_classifications.find(
        (item) => item.id === this.buildingClassificationId,
      ) || null
    );
  }

  get manualTargetCount(): number {
    return this.isManualBuilding
      ? (this.selectedBuildingClassification ? 1 : 0)
      : this.selectedEquipmentCount;
  }

  get familyOptions(): PreventiveFamilyOption[] {
    const map = new Map<number, PreventiveFamilyOption>();

    for (const item of this.equipment) {
      const family = item.familia;
      if (!family) continue;
      map.set(family.id, {
        id: family.id,
        key: family.key,
        nombre: family.nombre,
      });
    }

    return [...map.values()].sort((a, b) =>
      a.nombre.localeCompare(b.nombre, 'es'),
    );
  }

  get filteredEquipment(): PreventiveEquipment[] {
    const search = this.normalize(this.equipmentSearch);

    return this.equipment.filter((item) => {
      if (
        this.familyId !== null
        && item.familia_equipo_id !== this.familyId
      ) {
        return false;
      }

      if (!search) return true;

      return this.normalize(
        [
          item.codigo_interno,
          item.nombre,
          item.marca,
          item.familia?.nombre || '',
        ].join(' '),
      ).includes(search);
    });
  }

  get selectedEquipmentCount(): number {
    return this.selectedEquipmentIds.size;
  }

  get missingManualRequirements(): string[] {
    const missing: string[] = [];

    if (!this.selectedBranch) {
      missing.push('sucursal');
    }
    if (
      this.isManualEquipment
      && this.selectedEquipmentIds.size === 0
    ) {
      missing.push('al menos un equipo');
    }
    if (
      this.isManualBuilding
      && !this.selectedBuildingClassification
    ) {
      missing.push('clasificación de edificio');
    }
    if (!this.responsibleUsername) {
      missing.push('responsable');
    }
    if (!this.programmedDate) {
      missing.push('fecha programada');
    }
    if (!this.activity.trim()) {
      missing.push('actividad');
    }
    if (this.repeatEnabled && this.repeatIntervalWorkdays <= 0) {
      missing.push('intervalo de repetición');
    }
    if (
      this.repeatEnabled
      && this.programmedDate
      && !this.isBusinessDate(this.programmedDate)
    ) {
      missing.push('fecha inicial de lunes a viernes');
    }

    return missing;
  }

  get manualAddHelpText(): string {
    const missing = this.missingManualRequirements;

    if (missing.length === 0) {
      return (
        'Listo para agregar '
        + String(this.manualTargetCount)
        + (this.manualTargetCount === 1 ? ' preventivo.' : ' preventivos.')
      );
    }

    return (
      (missing.length === 1 ? 'Falta: ' : 'Faltan: ')
      + missing.join(', ')
      + '.'
    );
  }

  get canAddManualItems(): boolean {
    return Boolean(
      this.selectedBatch
      && this.selectedBatch.status === 'BORRADOR'
      && this.missingManualRequirements.length === 0
    );
  }

  get canValidate(): boolean {
    return Boolean(
      this.selectedBatch
      && this.selectedBatch.status === 'BORRADOR'
      && this.selectedBatch.items.length > 0
      && !this.saving,
    );
  }

  get canPublish(): boolean {
    if (
      !this.selectedBatch
      || this.selectedBatch.status !== 'BORRADOR'
      || !this.selectedBatch.items.length
      || this.saving
    ) {
      return false;
    }

    return this.selectedBatch.items.every(
      (item) => item.validation_status === 'VALIDO',
    );
  }

  get batchValidCount(): number {
    return (
      this.selectedBatch?.items.filter(
        (item) => item.validation_status === 'VALIDO',
      ).length || 0
    );
  }

  get batchErrorCount(): number {
    return (
      this.selectedBatch?.items.filter(
        (item) => item.validation_status === 'ERROR',
      ).length || 0
    );
  }

  get batchPendingCount(): number {
    return (
      this.selectedBatch?.items.filter(
        (item) => item.validation_status === 'PENDIENTE',
      ).length || 0
    );
  }

  loadInitialData(): void {
    this.loading = true;
    this.clearMessages();

    this.preventiveService.getContext().subscribe({
      next: (context) => {
        this.context = context;
        this.loadBatches();
      },
      error: (error) => {
        this.loading = false;
        this.setError(error, 'No se pudo cargar el contexto de programación.');
      },
    });
  }

  loadBatches(selectBatchId?: number): void {
    this.preventiveService.listBatches().subscribe({
      next: (response) => {
        this.batches = response.batches || [];
        this.loading = false;

        if (selectBatchId) {
          this.selectBatch(selectBatchId);
          return;
        }

        if (
          this.selectedBatch
          && !this.batches.some(
            (batch) => batch.id === this.selectedBatch?.id,
          )
        ) {
          this.selectedBatch = null;
        }
      },
      error: (error) => {
        this.loading = false;
        this.setError(error, 'No se pudieron cargar los lotes preventivos.');
      },
    });
  }

  selectBatch(batchId: number): void {
    this.loading = true;
    this.clearMessages();

    this.preventiveService.getBatch(batchId).subscribe({
      next: (batch) => {
        this.selectedBatch = batch;
        this.loading = false;
      },
      error: (error) => {
        this.loading = false;
        this.setError(error, 'No se pudo abrir el lote preventivo.');
      },
    });
  }

  createManualBatch(): void {
    const nombre = this.newBatchName.trim();
    if (!nombre) {
      this.errorMessage = 'Escribe un nombre para el lote.';
      return;
    }

    this.saving = true;
    this.clearMessages();

    this.preventiveService.createBatch({
      nombre,
      source_type: 'MANUAL',
      period_start: this.periodStart || null,
      period_end: this.periodEnd || null,
    }).subscribe({
      next: (batch) => {
        this.selectedBatch = batch;
        this.newBatchName = '';
        this.saving = false;
        this.successMessage = 'Lote borrador creado.';
        this.loadBatches(batch.id);
      },
      error: (error) => {
        this.saving = false;
        this.setError(error, 'No se pudo crear el lote.');
      },
    });
  }

  onBranchChange(): void {
    this.familyId = null;
    this.equipmentSearch = '';
    this.selectedEquipmentIds.clear();
    this.equipment = [];

    if (!this.branchId) {
      return;
    }

    this.loading = true;
    this.clearMessages();

    this.preventiveService.getEquipment(this.branchId).subscribe({
      next: (response) => {
        this.equipment = response.equipos || [];
        this.loading = false;
      },
      error: (error) => {
        this.loading = false;
        this.setError(error, 'No se pudieron cargar los equipos de la sucursal.');
      },
    });
  }

  onTargetTypeChange(): void {
    this.clearMessages();

    if (this.isManualBuilding) {
      this.familyId = null;
      this.equipmentSearch = '';
      this.clearEquipmentSelection();
      return;
    }

    this.buildingClassificationId = null;
  }

  toggleEquipment(inventoryId: number, checked: boolean): void {
    if (checked) {
      this.selectedEquipmentIds.add(inventoryId);
    } else {
      this.selectedEquipmentIds.delete(inventoryId);
    }
  }

  isEquipmentSelected(inventoryId: number): boolean {
    return this.selectedEquipmentIds.has(inventoryId);
  }

  selectAllVisibleEquipment(): void {
    for (const item of this.filteredEquipment) {
      this.selectedEquipmentIds.add(item.inventario_id);
    }
  }

  clearEquipmentSelection(): void {
    this.selectedEquipmentIds.clear();
  }

  addSelectedEquipment(): void {
    if (!this.canAddManualItems || !this.selectedBatch || !this.selectedBranch) {
      this.errorMessage =
        'Completa sucursal, objetivo, responsable, fecha y actividad.';
      return;
    }

    const common = {
      sucursal: this.selectedBranch.nombre,
      responsable: this.responsibleUsername,
      fecha_programada: this.programmedDate,
      repeat_enabled: this.repeatEnabled,
      repeat_interval_workdays: this.repeatEnabled
        ? this.repeatIntervalWorkdays
        : null,
      actividad: this.activity.trim(),
      observaciones: this.observations.trim() || null,
    };

    const items = this.isManualEquipment
      ? this.equipment
        .filter((item) =>
          this.selectedEquipmentIds.has(item.inventario_id)
        )
        .map((item) => ({
          ...common,
          target_type: 'EQUIPO' as const,
          codigo_equipo: item.codigo_interno,
          building_classification_id: null,
        }))
      : [{
          ...common,
          target_type: 'EDIFICIO' as const,
          codigo_equipo: null,
          building_classification_id:
            this.selectedBuildingClassification?.id || null,
        }];

    this.saving = true;
    this.clearMessages();

    this.preventiveService.addItems(
      this.selectedBatch.id,
      items,
    ).subscribe({
      next: (batch) => {
        this.selectedBatch = batch;
        this.saving = false;
        this.successMessage =
          String(items.length) + ' preventivos agregados al borrador.';
        this.clearEquipmentSelection();
        this.loadBatches();
      },
      error: (error) => {
        this.saving = false;
        this.setError(error, 'No se pudieron agregar los preventivos.');
      },
    });
  }

  validateSelectedBatch(): void {
    if (!this.selectedBatch || !this.canValidate) return;

    this.saving = true;
    this.clearMessages();

    this.preventiveService.validateBatch(this.selectedBatch.id).subscribe({
      next: (response) => {
        this.selectedBatch = response.batch;
        this.saving = false;
        this.successMessage =
          response.summary.errores === 0
            ? 'Lote validado y listo para publicar.'
            : 'Validación terminada con '
              + String(response.summary.errores)
              + ' renglones por corregir.';
        this.loadBatches();
      },
      error: (error) => {
        this.saving = false;
        this.setError(error, 'No se pudo validar el lote.');
      },
    });
  }

  publishSelectedBatch(): void {
    if (!this.selectedBatch || !this.canPublish) return;

    const batchId = this.selectedBatch.id;
    const itemCount = this.selectedBatch.items.length;

    const dialogRef = this.dialog.open(DialogoConfirmacionComponent, {
      data: {
        titulo: 'Publicar preventivos',
        mensaje:
          'Se crearán '
          + String(itemCount)
          + (itemCount === 1
            ? ' ticket preventivo. '
            : ' tickets preventivos. ')
          + 'Después de publicar, el lote ya no podrá editarse.',
        textoAceptar: 'Publicar',
        textoCancelar: 'Cancelar',
      },
      autoFocus: false,
      restoreFocus: true,
    });

    dialogRef.afterClosed().subscribe((confirmed) => {
      if (!confirmed) {
        return;
      }

      this.saving = true;
      this.clearMessages();

      this.preventiveService.publishBatch(batchId).subscribe({
        next: (response) => {
          this.selectedBatch = response.batch;
          this.saving = false;
          this.successMessage =
            'Lote publicado. Tickets generados: '
            + response.ticket_ids.join(', ');
          this.loadBatches();
        },
        error: (error) => {
          this.saving = false;
          this.setError(error, 'No se pudo publicar el lote.');
        },
      });
    });
  }

  saveItem(item: PreventiveDraftItem): void {
    if (!this.selectedBatch || this.selectedBatch.status !== 'BORRADOR') {
      return;
    }

    this.saving = true;
    this.clearMessages();

    this.preventiveService.updateItem(
      this.selectedBatch.id,
      item.id,
      {
        target_type: item.target_type_input || 'EQUIPO',
        sucursal: item.sucursal_input || '',
        codigo_equipo: item.codigo_equipo_input || null,
        building_classification_id:
          item.building_classification_input || null,
        responsable: item.responsable_input || '',
        fecha_programada: item.fecha_programada_input || '',
        repeat_enabled: item.repeat_enabled_input || '',
        repeat_interval_workdays:
          item.repeat_interval_workdays_input || null,
        actividad: item.actividad || '',
        observaciones: item.observaciones || null,
      },
    ).subscribe({
      next: () => {
        this.saving = false;
        this.successMessage = 'Renglón actualizado; vuelve a validar el lote.';
        this.selectBatch(this.selectedBatch?.id || 0);
        this.loadBatches();
      },
      error: (error) => {
        this.saving = false;
        this.setError(error, 'No se pudo actualizar el renglón.');
      },
    });
  }

  deleteItem(item: PreventiveDraftItem): void {
    if (!this.selectedBatch || this.selectedBatch.status !== 'BORRADOR') {
      return;
    }

    const batchId = this.selectedBatch.id;
    const targetLabel = this.itemTargetLabel(item);

    const dialogRef = this.dialog.open(DialogoConfirmacionComponent, {
      data: {
        titulo: 'Eliminar renglón',
        mensaje:
          'Se eliminará '
          + targetLabel
          + ' de este borrador. Esta acción no afecta tickets ya publicados.',
        textoAceptar: 'Eliminar',
        textoCancelar: 'Cancelar',
      },
      autoFocus: false,
      restoreFocus: true,
    });

    dialogRef.afterClosed().subscribe((confirmed) => {
      if (!confirmed) {
        return;
      }

      this.saving = true;
      this.clearMessages();

      this.preventiveService.deleteItem(batchId, item.id).subscribe({
        next: () => {
          this.saving = false;
          this.successMessage = 'Renglón eliminado.';
          this.selectBatch(batchId);
          this.loadBatches();
        },
        error: (error) => {
          this.saving = false;
          this.setError(error, 'No se pudo eliminar el renglón.');
        },
      });
    });
  }

  onImportFileSelected(event: Event): void {
    const input = event.target as HTMLInputElement;
    this.importFile = input.files?.[0] || null;
  }

  importSelectedFile(): void {
    if (!this.importFile) {
      this.errorMessage = 'Selecciona un archivo .xlsx o .csv.';
      return;
    }

    this.saving = true;
    this.clearMessages();

    this.preventiveService.importBatch(
      this.importFile,
      {
        nombre: this.newBatchName.trim() || this.importFile.name,
        period_start: this.periodStart || undefined,
        period_end: this.periodEnd || undefined,
      },
    ).subscribe({
      next: (response) => {
        this.selectedBatch = response.batch;
        this.importFile = null;
        this.saving = false;
        this.successMessage =
          response.summary.errores === 0
            ? 'Archivo cargado y validado.'
            : 'Archivo cargado con '
              + String(response.summary.errores)
              + ' renglones por corregir.';
        this.loadBatches(response.batch.id);
      },
      error: (error) => {
        this.saving = false;
        this.setError(error, 'No se pudo cargar la plantilla.');
      },
    });
  }

  downloadTemplate(): void {
    this.clearMessages();

    this.preventiveService.downloadTemplate().subscribe({
      next: (blob) => {
        const url = URL.createObjectURL(blob);
        const anchor = document.createElement('a');
        anchor.href = url;
        anchor.download = 'plantilla_programacion_preventiva.xlsx';
        anchor.click();
        URL.revokeObjectURL(url);
      },
      error: (error) => {
        this.setError(error, 'No se pudo descargar la plantilla.');
      },
    });
  }

  isItemBuilding(item: PreventiveDraftItem): boolean {
    return this.normalize(item.target_type_input || 'EQUIPO')
      === 'edificio';
  }

  onItemTargetTypeChange(item: PreventiveDraftItem): void {
    if (this.isItemBuilding(item)) {
      item.codigo_equipo_input = null;
      return;
    }

    item.building_classification_input = null;
  }

  itemTargetLabel(item: PreventiveDraftItem): string {
    if (item.target_type === 'EDIFICIO') {
      return item.building_classification?.label
        || item.building_classification_input
        || 'Edificio';
    }

    return item.codigo_equipo_input || 'Equipo';
  }

  onRepeatEnabledChange(): void {
    if (this.repeatEnabled && this.repeatIntervalWorkdays <= 0) {
      this.repeatIntervalWorkdays = 20;
    }
  }

  isItemRecurringInput(item: PreventiveDraftItem): boolean {
    const value = this.normalize(item.repeat_enabled_input || '');
    return (
      value === 'si'
      || value === 'sí'
      || value === 'true'
      || value === '1'
    );
  }

  onItemRepeatInputChange(item: PreventiveDraftItem): void {
    if (!this.isItemRecurringInput(item)) {
      item.repeat_interval_workdays_input = null;
    }
  }

  itemRecurrenceLabel(item: PreventiveDraftItem): string {
    if (!item.repeat_enabled) {
      return 'Una vez';
    }

    const interval = item.repeat_interval_workdays;
    if (!interval) {
      return 'Recurrente';
    }

    return 'Cada ' + String(interval) + ' días hábiles';
  }

  itemStatusLabel(item: PreventiveDraftItem): string {
    const labels = {
      PENDIENTE: 'Pendiente',
      VALIDO: 'Válido',
      ERROR: 'Error',
    };
    return labels[item.validation_status] || item.validation_status;
  }

  trackBatch(_: number, batch: PreventiveBatchSummary): number {
    return batch.id;
  }

  trackEquipment(_: number, item: PreventiveEquipment): number {
    return item.inventario_id;
  }

  trackItem(_: number, item: PreventiveDraftItem): number {
    return item.id;
  }

  private isBusinessDate(value: string): boolean {
    const parts = value.split('-').map((part) => Number(part));
    if (parts.length !== 3 || parts.some((part) => !Number.isFinite(part))) {
      return false;
    }

    const [year, month, day] = parts;
    const parsed = new Date(year, month - 1, day);
    const weekday = parsed.getDay();
    return weekday >= 1 && weekday <= 5;
  }

  private clearMessages(): void {
    this.errorMessage = '';
    this.successMessage = '';
  }

  private setError(error: any, fallback: string): void {
    this.errorMessage =
      error?.error?.mensaje
      || error?.error?.detail
      || error?.message
      || fallback;
  }

  private normalize(value: string): string {
    return String(value || '')
      .trim()
      .toLocaleLowerCase('es-MX');
  }
}
