import { CommonModule } from '@angular/common';
import { Component, DestroyRef, OnInit, inject } from '@angular/core';
import { FormControl, FormGroup, ReactiveFormsModule, Validators } from '@angular/forms';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { MatButtonModule } from '@angular/material/button';
import { MatCheckboxModule } from '@angular/material/checkbox';
import { MatDialogModule } from '@angular/material/dialog';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatSelectModule } from '@angular/material/select';
import { EMPTY, catchError, exhaustMap, timer } from 'rxjs';

import {
  IventasTemplateCategory,
  IventasTemplateUploadStatus,
  IventasTemplateUploadsResponse,
} from './marketing-campaign-v2.models';
import { MarketingCampaignV2Service } from './marketing-campaign-v2.service';

interface FieldSelection {
  start: number;
  end: number;
  example: string;
}

@Component({
  selector: 'app-marketing-campaign-v2-template-upload-dialog',
  standalone: true,
  imports: [
    CommonModule, ReactiveFormsModule, MatButtonModule, MatCheckboxModule,
    MatDialogModule, MatFormFieldModule, MatInputModule, MatSelectModule,
  ],
  templateUrl: './marketing-campaign-v2-template-upload-dialog.component.html',
  styleUrls: ['./marketing-campaign-v2-template-upload-dialog.component.css'],
})
export class MarketingCampaignV2TemplateUploadDialogComponent implements OnInit {
  private readonly api = inject(MarketingCampaignV2Service);
  private readonly destroyRef = inject(DestroyRef);

  readonly form = new FormGroup({
    name: new FormControl('', { nonNullable: true, validators: Validators.pattern(/^[a-z0-9_]{1,255}$/) }),
    message: new FormControl('', { nonNullable: true, validators: Validators.required }),
    category: new FormControl<IventasTemplateCategory>('MARKETING', { nonNullable: true }),
    branchIds: new FormControl<number[]>([], { nonNullable: true, validators: Validators.required }),
  });
  readonly statusLabels: Record<IventasTemplateUploadStatus, string> = {
    QUEUED: 'Pendiente', RUNNING: 'Procesando', FINISHED: 'Terminado',
    SUBMITTED: 'Registrada en iVentas', EXISTS: 'Ya existía', ERROR: 'Error', VERIFY: 'Verificar en iVentas',
  };

  data: IventasTemplateUploadsResponse | null = null;
  fields: FieldSelection[] = [];
  buttons: FormControl<string>[] = [];
  image: File | null = null;
  loadingError = '';
  error = '';
  notice = '';
  saving = false;

  ngOnInit(): void {
    this.form.controls.message.valueChanges
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe(() => {
        if (this.fields.length) {
          this.fields = [];
          this.notice = 'Cambiaste el mensaje. Vuelve a marcar los campos que quieras personalizar.';
        }
      });

    timer(0, 5000).pipe(
      exhaustMap(() => this.api.listIventasTemplateUploads().pipe(
        catchError(() => {
          this.loadingError = 'No fue posible consultar las cargas de iVentas.';
          return EMPTY;
        }),
      )),
      takeUntilDestroyed(this.destroyRef),
    ).subscribe(result => {
      this.data = result;
      this.loadingError = '';
    });
  }

  get canSubmit(): boolean {
    const { name, message } = this.form.getRawValue();
    return Boolean(this.data?.enabled && !this.saving && this.form.valid && name.trim() && message.trim()
      && this.buttons.every(button => button.value.trim()));
  }

  get allBranchesSelected(): boolean {
    return Boolean(this.data?.targets.length) && this.form.controls.branchIds.value.length === this.data?.targets.length;
  }

  toggleAllBranches(checked: boolean): void {
    this.form.controls.branchIds.setValue(checked ? this.data?.targets.map(branch => branch.sucursal_id) ?? [] : []);
  }

  markField(textarea: HTMLTextAreaElement): void {
    const { selectionStart: start, selectionEnd: end } = textarea;
    const example = textarea.value.slice(start, end);
    this.error = '';
    this.notice = '';
    if (!/[\p{L}\p{N}]/u.test(example)) {
      this.error = 'Selecciona en el mensaje la palabra que quieras convertir en campo.';
      return;
    }
    if (this.fields.some(field => start < field.end && end > field.start)) {
      this.error = 'La selección se cruza con un campo que ya marcaste.';
      return;
    }
    this.fields = [...this.fields, { start, end, example }].sort((a, b) => a.start - b.start);
  }

  removeField(index: number): void {
    this.fields = this.fields.filter((_, position) => position !== index);
  }

  addButton(): void {
    this.buttons.push(new FormControl('', { nonNullable: true }));
  }

  removeButton(index: number): void {
    this.buttons.splice(index, 1);
  }

  setImage(input: HTMLInputElement): void {
    this.image = input.files?.[0] ?? null;
  }

  submit(): void {
    if (!this.canSubmit) { return; }
    this.error = '';
    this.notice = '';
    const request = this.form.getRawValue();
    const lastField = this.fields.at(-1);
    if (lastField && !/[\p{L}\p{N}]/u.test(request.message.slice(lastField.end))) {
      this.error = 'Escribe una palabra después del último campo.';
      return;
    }
    this.saving = true;
    const payload = new FormData();
    payload.append('template', JSON.stringify({
      name: request.name,
      message: request.message,
      category: request.category,
      branch_ids: request.branchIds,
      fields: this.fields.map(({ start, end }) => ({ start, end })),
      buttons: this.buttons.map(button => button.value.trim()),
    }));
    if (this.image) {
      payload.append('image', this.image);
    }
    this.api.createIventasTemplateUpload(payload).pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: row => {
        this.saving = false;
        this.notice = `Carga #${row.id} puesta en cola.`;
        if (this.data) {
          this.data = { ...this.data, rows: [row, ...this.data.rows.filter(item => item.id !== row.id)] };
        }
      },
      error: response => {
        this.saving = false;
        this.error = response.error?.message ?? 'No fue posible iniciar la carga.';
      },
    });
  }
}
