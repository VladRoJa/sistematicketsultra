import { CommonModule } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import { Component, DestroyRef, EventEmitter, Inject, OnInit, Output, inject } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { MatButtonModule } from '@angular/material/button';
import { MAT_DIALOG_DATA, MatDialogModule, MatDialogRef } from '@angular/material/dialog';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatSelectModule } from '@angular/material/select';

import {
  CampaignV2AudienceDefinitionRequest,
  CampaignV2ObservedFamily,
  CampaignV2TariffClassificationResult,
  CampaignV2UnclassifiedTariffRow,
} from './marketing-campaign-v2.models';
import { MarketingCampaignV2Service } from './marketing-campaign-v2.service';

export interface MarketingCampaignV2TariffClassifierDialogData {
  audience: CampaignV2AudienceDefinitionRequest;
  families: CampaignV2ObservedFamily[];
}

interface TariffClassifierRowState extends CampaignV2UnclassifiedTariffRow {
  categoriaTarifa: string;
  audienceFamily: CampaignV2ObservedFamily | '';
  saving: boolean;
  saved: boolean;
  error: string;
}

@Component({
  selector: 'app-marketing-campaign-v2-tariff-classifier-dialog',
  standalone: true,
  imports: [
    CommonModule,
    MatButtonModule,
    MatDialogModule,
    MatFormFieldModule,
    MatInputModule,
    MatProgressSpinnerModule,
    MatSelectModule,
  ],
  templateUrl: './marketing-campaign-v2-tariff-classifier-dialog.component.html',
  styleUrls: ['./marketing-campaign-v2-tariff-classifier-dialog.component.css'],
})
export class MarketingCampaignV2TariffClassifierDialogComponent implements OnInit {
  private readonly service = inject(MarketingCampaignV2Service);
  private readonly destroyRef = inject(DestroyRef);
  private readonly dialogRef = inject(MatDialogRef<MarketingCampaignV2TariffClassifierDialogComponent>);

  @Output() readonly classificationSaved = new EventEmitter<CampaignV2TariffClassificationResult>();

  rows: TariffClassifierRowState[] = [];
  loading = false;
  error = '';
  totalUnclassifiedRows = 0;
  unkeyedRowCount = 0;

  constructor(
    @Inject(MAT_DIALOG_DATA)
    readonly data: MarketingCampaignV2TariffClassifierDialogData,
  ) {}

  ngOnInit(): void {
    this.load();
  }

  close(): void {
    this.dialogRef.close();
  }

  setCategory(row: TariffClassifierRowState, event: Event): void {
    row.categoriaTarifa = (event.target as HTMLInputElement).value;
    row.saved = false;
    row.error = '';
  }

  setFamily(row: TariffClassifierRowState, family: CampaignV2ObservedFamily): void {
    row.audienceFamily = family;
    row.saved = false;
    row.error = '';
  }

  canSave(row: TariffClassifierRowState): boolean {
    return Boolean(row.categoriaTarifa.trim() && row.audienceFamily && !row.saving);
  }

  save(row: TariffClassifierRowState): void {
    if (!this.canSave(row) || !row.audienceFamily) {
      row.error = 'Captura categoría y familia.';
      return;
    }

    row.saving = true;
    row.error = '';
    this.service.classifyTariff(
      row.tarifa_key,
      {
        categoria_tarifa: row.categoriaTarifa.trim(),
        audience_family: row.audienceFamily,
      },
      this.data.audience,
    )
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: result => {
          row.saving = false;
          row.saved = true;
          row.categoriaTarifa = result.categoria_tarifa;
          row.audienceFamily = result.audience_family;
          this.classificationSaved.emit(result);
        },
        error: (error: HttpErrorResponse) => {
          row.saving = false;
          row.error = this.errorMessage(error);
        },
      });
  }

  familyLabel(family: CampaignV2ObservedFamily): string {
    switch (family) {
      case 'DOMICILIADO': return 'Domiciliado';
      case 'TRIMESTRAL': return 'Trimestral';
      case 'CONVENIO': return 'Convenio';
      case 'SEMESTRE': return 'Semestre';
      case 'ESTUDIANTE': return 'Estudiante';
      case 'MES': return 'Mes';
      case 'OUT_OF_SEGMENT': return 'Fuera de segmento';
    }
  }

  private load(): void {
    this.loading = true;
    this.error = '';
    this.service.listUnclassifiedTariffs(this.data.audience)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: result => {
          this.loading = false;
          this.totalUnclassifiedRows = result.total_unclassified_rows;
          this.unkeyedRowCount = result.unkeyed_row_count;
          this.rows = result.rows.map(row => ({
            ...row,
            categoriaTarifa: '',
            audienceFamily: '',
            saving: false,
            saved: false,
            error: '',
          }));
        },
        error: (error: HttpErrorResponse) => {
          this.loading = false;
          this.error = this.errorMessage(error);
        },
      });
  }

  private errorMessage(error: HttpErrorResponse): string {
    const server = error.error as { message?: string } | null;
    if (error.status === 403) {
      return 'No tienes permiso para catalogar tarifas Campaign V2.';
    }
    return server?.message || 'No fue posible cargar o guardar el catálogo de tarifas.';
  }
}
