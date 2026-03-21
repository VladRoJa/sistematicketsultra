//frontend\src\app\warehouse\warehouse-home.component.ts


import { CommonModule } from '@angular/common';
import { Component, ElementRef, OnInit, ViewChild, inject } from '@angular/core';


import { WarehouseUploadDetail, WarehouseUploadListItem, WarehouseUploadsService, WarehouseCreateUploadRequest,WarehouseUploadAuditItem,} from './services/warehouse-uploads.service';
import { WarehouseCatalogOption, WarehouseCatalogsService, WarehouseReportTypeCatalogOption, } from './services/warehouse-catalogs.service';







interface WarehouseUploadRow extends WarehouseUploadListItem {
  created_at_display: string;
}

interface WarehouseUploadFormState {
  file: File | null;
  report_type_key: string;
  cutoff_date: string;
  date_from: string;
  date_to: string;
}

interface WarehouseSelectedReportTypeContext {
  reportType: WarehouseReportTypeCatalogOption | null;
  periodType: string;
}

interface WarehouseUploadAuditRow extends WarehouseUploadAuditItem {
  created_at_display: string;
  details_display: string;
}

@Component({
  selector: 'app-warehouse-home',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './warehouse-home.component.html',
  styleUrls: ['./warehouse-home.component.css'],
})
export class WarehouseHomeComponent implements OnInit {
  private readonly warehouseUploadsService = inject(WarehouseUploadsService);
  private readonly warehouseCatalogsService = inject(WarehouseCatalogsService);
  @ViewChild('warehouseFileInput') warehouseFileInput?: ElementRef<HTMLInputElement>;

  selectedUploadDetail: WarehouseUploadDetail | null = null;
  sources: WarehouseCatalogOption[] = [];
  families: WarehouseCatalogOption[] = [];
  operationalRoles: WarehouseCatalogOption[] = [];
  reportTypes: WarehouseReportTypeCatalogOption[] = [];
  catalogsErrorMessage = '';
  uploadForm: WarehouseUploadFormState = {
    file: null,
    report_type_key: '',
    cutoff_date: '',
    date_from: '',
    date_to: '',
  };

  selectedReportTypeContext: WarehouseSelectedReportTypeContext = {
    reportType: null,
    periodType: '',
  };

  uploadErrorMessage = '';
  uploadSuccessMessage = '';
  selectedUploadAudit: WarehouseUploadAuditRow[] = [];
  auditErrorMessage = '';

  uploads: WarehouseUploadRow[] = [];
  isLoading = false;
  errorMessage = '';

  ngOnInit(): void {
    this.loadCatalogs();
    this.loadUploads();
  }

  loadUploads(): void {
    this.isLoading = true;
    this.errorMessage = '';

    this.warehouseUploadsService.getUploads().subscribe({
      next: (response) => {
        const items = response.items || [];
        this.uploads = items.map((item) => this.mapUploadRow(item));
        this.isLoading = false;
      },
      error: () => {
        this.uploads = [];
        this.errorMessage = 'No se pudo cargar el histórico de Warehouse.';
        this.isLoading = false;
      },
    });
  }

  private mapUploadRow(item: WarehouseUploadListItem): WarehouseUploadRow {
    return {
      ...item,
      created_at_display: this.formatDateTime(item.created_at),
    };
  }

  private formatDateTime(value: string | null): string {
    if (!value) {
      return '';
    }

    const date = new Date(value);
    if (Number.isNaN(date.getTime())) {
      return value;
    }

    return new Intl.DateTimeFormat('es-MX', {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      hour12: false,
    }).format(date);
  }

  downloadUpload(upload: WarehouseUploadRow): void {
  this.warehouseUploadsService.downloadUpload(upload.id).subscribe({
    next: (blob) => {
      const objectUrl = window.URL.createObjectURL(blob);
      const anchor = document.createElement('a');

      anchor.href = objectUrl;
      anchor.download = upload.original_filename;
      anchor.click();

      window.URL.revokeObjectURL(objectUrl);
    },
    error: () => {
      this.errorMessage = `No se pudo descargar el archivo ${upload.original_filename}.`;
    },
  });
}

viewUploadDetail(upload: WarehouseUploadRow): void {
  this.errorMessage = '';

  this.warehouseUploadsService.getUploadDetail(upload.id).subscribe({
    next: (detail) => {
      this.selectedUploadDetail = detail;
    },
    error: () => {
      this.selectedUploadDetail = null;
      this.errorMessage = `No se pudo cargar el detalle del upload ${upload.id}.`;
    },
  });
}

archiveUpload(upload: WarehouseUploadRow): void {
  this.errorMessage = '';

  this.warehouseUploadsService.archiveUpload(upload.id).subscribe({
    next: () => {
      const selectedId = this.selectedUploadDetail?.id ?? null;

      this.loadUploads();

      if (selectedId === upload.id) {
        this.viewUploadDetail(upload);
      }
    },
    error: () => {
      this.errorMessage = `No se pudo archivar el upload ${upload.id}.`;
    },
  });
}

loadCatalogs(): void {
  this.catalogsErrorMessage = '';

  this.warehouseCatalogsService.getCatalogs().subscribe({
    next: (response) => {
      this.sources = response.sources || [];
      this.families = response.families || [];
      this.operationalRoles = response.operational_roles || [];
      this.reportTypes = response.report_types || [];
    },
    error: () => {
      this.sources = [];
      this.families = [];
      this.operationalRoles = [];
      this.reportTypes = [];
      this.catalogsErrorMessage = 'No se pudieron cargar los catálogos de Warehouse.';
    },
  });
}

onReportTypeChanged(reportTypeKey: string): void {
  this.uploadForm.report_type_key = reportTypeKey;
  this.uploadForm.cutoff_date = '';
  this.uploadForm.date_from = '';
  this.uploadForm.date_to = '';

  const selectedReportType =
    this.reportTypes.find((item) => item.key === reportTypeKey) || null;

  this.selectedReportTypeContext = {
    reportType: selectedReportType,
    periodType: selectedReportType?.default_period_type || '',
  };
}

onFileSelected(event: Event): void {
  const input = event.target as HTMLInputElement;
  const file = input.files && input.files.length > 0 ? input.files[0] : null;
  this.uploadForm.file = file;
}

isDailyPeriodSelected(): boolean {
  return this.selectedReportTypeContext.periodType === 'diario';
}

isRangePeriodSelected(): boolean {
  return this.selectedReportTypeContext.periodType === 'rango';
}

submitUpload(): void {
  this.uploadErrorMessage = '';
  this.uploadSuccessMessage = '';
  this.errorMessage = '';

  const validationError = this.validateUploadForm();
  if (validationError) {
    this.uploadErrorMessage = validationError;
    return;
  }

  const payload = this.buildCreateUploadPayload();
  if (!payload) {
    this.uploadErrorMessage = 'No se pudo construir el payload del upload.';
    return;
  }

  this.warehouseUploadsService.createUpload(payload).subscribe({
    next: (response) => {
      this.uploadSuccessMessage = `Upload creado correctamente con id ${response.upload_id}.`;
      this.resetUploadForm();
      this.loadUploads();
    },
    error: (error) => {
      const detail = error?.error?.detail || '';
      this.uploadErrorMessage = detail || 'No se pudo crear el upload en Warehouse.';
    },
  });
}

private validateUploadForm(): string {
  if (!this.uploadForm.file) {
    return 'Debes seleccionar un archivo.';
  }

  if (!this.uploadForm.report_type_key) {
    return 'Debes seleccionar un tipo de reporte.';
  }

  if (this.isDailyPeriodSelected() && !this.uploadForm.cutoff_date) {
    return 'Debes capturar cutoff date para un reporte diario.';
  }

  if (this.isRangePeriodSelected()) {
    if (!this.uploadForm.date_from || !this.uploadForm.date_to) {
      return 'Debes capturar date from y date to para un reporte de rango.';
    }
  }

  return '';
}

private buildCreateUploadPayload(): WarehouseCreateUploadRequest | null {
  if (!this.uploadForm.file || !this.uploadForm.report_type_key) {
    return null;
  }

  return {
    file: this.uploadForm.file,
    report_type_key: this.uploadForm.report_type_key,
    cutoff_date: this.uploadForm.cutoff_date || undefined,
    date_from: this.uploadForm.date_from || undefined,
    date_to: this.uploadForm.date_to || undefined,
  };
}

private resetUploadForm(): void {
  this.uploadForm = {
    file: null,
    report_type_key: '',
    cutoff_date: '',
    date_from: '',
    date_to: '',
  };

  this.selectedReportTypeContext = {
    reportType: null,
    periodType: '',
  };

  if (this.warehouseFileInput?.nativeElement) {
    this.warehouseFileInput.nativeElement.value = '';
  }
}

clearSelectedUploadDetail(): void {
  this.selectedUploadDetail = null;
  this.selectedUploadAudit = [];
  this.auditErrorMessage = '';
}

viewUploadAudit(upload: WarehouseUploadRow): void {
  this.auditErrorMessage = '';

  this.warehouseUploadsService.getUploadAudit(upload.id).subscribe({
    next: (response) => {
      const items = response.items || [];
      this.selectedUploadAudit = items.map((item) => this.mapAuditRow(item));
    },
    error: () => {
      this.selectedUploadAudit = [];
      this.auditErrorMessage = `No se pudo cargar la auditoría del upload ${upload.id}.`;
    },
  });
}

clearSelectedUploadAudit(): void {
  this.selectedUploadAudit = [];
  this.auditErrorMessage = '';
}


private mapAuditRow(item: WarehouseUploadAuditItem): WarehouseUploadAuditRow {
  return {
    ...item,
    created_at_display: this.formatDateTime(item.created_at),
    details_display: this.formatAuditDetails(item.details),
  };
}

private formatAuditDetails(details: Record<string, unknown> | null): string {
  if (!details) {
    return '';
  }

  const entries = Object.entries(details);
  if (entries.length === 0) {
    return '';
  }

  return entries
    .map(([key, value]) => `${key}: ${value ?? '—'}`)
    .join(' | ');
}
}