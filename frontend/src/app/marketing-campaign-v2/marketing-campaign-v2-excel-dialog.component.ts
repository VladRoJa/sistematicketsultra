import { CommonModule } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import { Component, DestroyRef, OnInit, inject } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormControl, ReactiveFormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatCheckboxModule } from '@angular/material/checkbox';
import { MatDialogModule, MatDialogRef } from '@angular/material/dialog';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatSelectModule } from '@angular/material/select';
import {
  CampaignV2DispatchTemplate, CampaignV2ExcelFrozen,
  CampaignV2ExcelPreview, CampaignV2Purpose,
} from './marketing-campaign-v2.models';
import { MarketingCampaignV2Service } from './marketing-campaign-v2.service';

@Component({
  selector: 'app-marketing-campaign-v2-excel-dialog',
  standalone: true,
  imports: [
    CommonModule, ReactiveFormsModule, MatButtonModule, MatCheckboxModule,
    MatDialogModule, MatFormFieldModule, MatInputModule, MatSelectModule,
  ],
  templateUrl: './marketing-campaign-v2-excel-dialog.component.html',
  styleUrls: ['./marketing-campaign-v2-excel-dialog.component.css'],
})
export class MarketingCampaignV2ExcelDialogComponent implements OnInit {
  private readonly api = inject(MarketingCampaignV2Service);
  private readonly destroyRef = inject(DestroyRef);
  private readonly dialogRef = inject(MatDialogRef<MarketingCampaignV2ExcelDialogComponent>);

  readonly name = new FormControl('', { nonNullable: true });
  readonly purpose = new FormControl<CampaignV2Purpose>('REACTIVATION', { nonNullable: true });
  readonly templateId = new FormControl<number | null>(null);
  readonly confirmFreeze = new FormControl(false, { nonNullable: true });

  templates: CampaignV2DispatchTemplate[] = [];
  selectedFile: File | null = null;
  preview: CampaignV2ExcelPreview | null = null;
  frozen: CampaignV2ExcelFrozen | null = null;
  loading = false;
  previewing = false;
  freezing = false;
  error = '';

  ngOnInit(): void {
    this.loadTemplates();
    this.name.valueChanges.pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe(() => this.invalidatePreview());
    this.purpose.valueChanges.pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe(() => this.invalidatePreview());
    this.templateId.valueChanges.pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe(() => this.invalidatePreview());
  }

  get availableTemplates(): CampaignV2DispatchTemplate[] {
    return this.templates.filter(template =>
      template.is_active &&
      (!template.purposes.length || template.purposes.includes(this.purpose.value)),
    );
  }

  get canPreview(): boolean {
    const filename = this.selectedFile?.name.toLowerCase() ?? '';
    return !this.loading && !this.previewing && !this.freezing && !this.frozen &&
      (filename.endsWith('.xlsx') || filename.endsWith('.csv')) &&
      Boolean(this.selectedFile && this.selectedFile.size <= 5 * 1024 * 1024) &&
      this.name.value.trim().length > 0 && this.name.value.trim().length <= 255 &&
      this.availableTemplates.some(row => row.id === this.templateId.value);
  }

  get canFreeze(): boolean {
    return this.canPreview && this.preview !== null && this.confirmFreeze.value;
  }

  get branchRows(): { name: string; count: number }[] {
    return Object.entries(this.preview?.branch_counts ?? {})
      .map(([name, count]) => ({ name, count }))
      .sort((a, b) => a.name.localeCompare(b.name));
  }

  onFileChange(event: Event): void {
    const input = event.target as HTMLInputElement;
    this.selectedFile = input.files?.[0] ?? null;
    this.invalidatePreview();
  }

  close(): void {
    this.dialogRef.close(Boolean(this.frozen));
  }

  private invalidatePreview(): void {
    this.preview = null;
    this.confirmFreeze.setValue(false, { emitEvent: false });
    this.error = '';
  }

  loadTemplates(): void {
    this.loading = true;
    this.api.listDispatchTemplatesAdmin()
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: response => {
          this.templates = response.rows;
          this.loading = false;
        },
        error: (error: HttpErrorResponse) => {
          this.loading = false;
          this.error = this.errorText(error, 'No se cargó el catálogo de plantillas.');
        },
      });
  }

  previewFile(): void {
    if (!this.canPreview || !this.selectedFile || this.templateId.value === null) { return; }
    this.previewing = true;
    this.error = '';
    this.api.previewExcel(
      this.selectedFile, this.name.value.trim(), this.purpose.value, this.templateId.value,
    ).pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: response => {
        this.previewing = false;
        this.preview = response;
      },
      error: (error: HttpErrorResponse) => {
        this.previewing = false;
        this.error = this.errorText(error, 'No se pudo validar la audiencia.');
      },
    });
  }

  freezeFile(): void {
    if (!this.canFreeze || !this.selectedFile || !this.preview || this.templateId.value === null) { return; }
    this.freezing = true;
    this.error = '';
    this.api.freezeExcel(
      this.selectedFile, this.name.value.trim(), this.purpose.value,
      this.templateId.value, this.preview.preview_fingerprint,
    ).pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: response => {
        this.freezing = false;
        this.frozen = response;
      },
      error: (error: HttpErrorResponse) => {
        this.freezing = false;
        this.invalidatePreview();
        this.error = this.errorText(error, 'No se pudo congelar la campaña.');
      },
    });
  }

  private errorText(error: HttpErrorResponse, fallback: string): string {
    return String(error.error?.message || fallback);
  }
}
