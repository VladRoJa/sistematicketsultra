//frontend\src\app\warehouse\warehouse-home.component.ts


import { CommonModule } from '@angular/common';
import { Component, OnInit, inject } from '@angular/core';
import {
  WarehouseUploadDetail,
  WarehouseUploadListItem,
  WarehouseUploadsService,
} from './services/warehouse-uploads.service';

interface WarehouseUploadRow extends WarehouseUploadListItem {
  created_at_display: string;
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

  selectedUploadDetail: WarehouseUploadDetail | null = null;



  uploads: WarehouseUploadRow[] = [];
  isLoading = false;
  errorMessage = '';

  ngOnInit(): void {
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

}