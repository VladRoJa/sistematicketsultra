import { CommonModule } from '@angular/common';
import { Component, DestroyRef, OnInit, inject } from '@angular/core';
import { FormControl, FormGroup, ReactiveFormsModule, Validators } from '@angular/forms';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { MatDialogModule } from '@angular/material/dialog';
import { EMPTY, catchError, exhaustMap, pairwise, startWith, timer } from 'rxjs';

import {
  IventasTemplateCategory,
  IventasTemplateUpload,
  IventasTemplateUploadStatus,
  IventasTemplateUploadTarget,
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
  imports: [CommonModule, ReactiveFormsModule, MatDialogModule],
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
  readonly branchSearch = new FormControl('', { nonNullable: true });
  readonly uploadImageLimit = 5 * 1024 * 1024;

  data: IventasTemplateUploadsResponse | null = null;
  view: 'form' | 'history' = 'form';
  expandedUploadId: number | null = null;
  fields: FieldSelection[] = [];
  buttons: FormControl<string>[] = [];
  image: File | null = null;
  loadingError = '';
  fieldFeedback = '';
  imageError = '';
  error = '';
  notice = '';
  saving = false;

  ngOnInit(): void {
    this.form.controls.message.valueChanges
      .pipe(startWith(this.form.controls.message.value), pairwise(), takeUntilDestroyed(this.destroyRef))
      .subscribe(([previous, current]) => this.reconcileFields(previous, current));

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
      && !this.imageError && this.buttons.every(button => button.value.trim()));
  }

  get visibleBranches(): IventasTemplateUploadTarget[] {
    const search = this.normalizeSearch(this.branchSearch.value);
    return (this.data?.targets ?? []).filter(branch => this.normalizeSearch(branch.sucursal_canon).includes(search));
  }

  get allVisibleBranchesSelected(): boolean {
    const branches = this.visibleBranches;
    return branches.length > 0 && branches.every(branch => this.isBranchSelected(branch.sucursal_id));
  }

  get someVisibleBranchesSelected(): boolean {
    return !this.allVisibleBranchesSelected && this.visibleBranches.some(branch => this.isBranchSelected(branch.sucursal_id));
  }

  branchLabel(code: string): string {
    return code.replace(/_/g, ' ');
  }

  isBranchSelected(id: number): boolean {
    return this.form.controls.branchIds.value.includes(id);
  }

  toggleBranch(id: number, checked: boolean): void {
    this.updateBranches([id], checked);
  }

  toggleVisibleBranches(checked: boolean): void {
    this.updateBranches(this.visibleBranches.map(branch => branch.sucursal_id), checked);
  }

  trackBranch(_index: number, branch: IventasTemplateUploadTarget): number {
    return branch.sucursal_id;
  }

  trackUpload(_index: number, row: IventasTemplateUpload): number {
    return row.id;
  }

  toggleUpload(id: number): void {
    this.expandedUploadId = this.expandedUploadId === id ? null : id;
  }

  markField(textarea: HTMLTextAreaElement): void {
    const { selectionStart: start, selectionEnd: end } = textarea;
    const example = textarea.value.slice(start, end);
    this.fieldFeedback = '';
    if (!/[\p{L}\p{N}]/u.test(example)) {
      this.fieldFeedback = 'Selecciona en el mensaje la palabra que quieras convertir en campo.';
      return;
    }
    if (this.fields.some(field => start < field.end && end > field.start)) {
      this.fieldFeedback = 'La selección se cruza con un campo que ya marcaste.';
      return;
    }
    this.fields = [...this.fields, { start, end, example }].sort((a, b) => a.start - b.start);
  }

  removeField(index: number): void {
    this.fieldFeedback = '';
    this.fields = this.fields.filter((_, position) => position !== index);
  }

  addButton(): void {
    this.buttons.push(new FormControl('', { nonNullable: true }));
  }

  removeButton(index: number): void {
    this.buttons.splice(index, 1);
  }

  setImage(input: HTMLInputElement): void {
    this.imageError = '';
    const file = input.files?.[0];
    if (!file) { return; }
    if (file.size > this.uploadImageLimit || !/\.(png|jpe?g)$/i.test(file.name)) {
      this.imageError = 'Elige una imagen PNG o JPEG de hasta 5 MB.';
      input.value = '';
      return;
    }
    this.image = file;
  }

  removeImage(input: HTMLInputElement): void {
    this.image = null;
    this.imageError = '';
    input.value = '';
  }

  submit(): void {
    if (!this.canSubmit) { return; }
    this.error = '';
    this.notice = '';
    const request = this.form.getRawValue();
    const lastField = this.fields.at(-1);
    if (lastField && !/[\p{L}\p{N}]/u.test(request.message.slice(lastField.end))) {
      this.fieldFeedback = 'Escribe una palabra después del último campo.';
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
        this.notice = `Carga #${row.id} registrada.`;
        this.expandedUploadId = row.id;
        this.view = 'history';
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

  private updateBranches(ids: number[], checked: boolean): void {
    const selected = new Set(this.form.controls.branchIds.value);
    for (const id of ids) {
      if (checked) { selected.add(id); }
      else { selected.delete(id); }
    }
    this.form.controls.branchIds.setValue([...selected]);
  }

  private normalizeSearch(value: string): string {
    return this.branchLabel(value).normalize('NFD').replace(/\p{M}/gu, '').trim().toLowerCase();
  }

  private reconcileFields(previous: string, current: string): void {
    this.fieldFeedback = '';
    if (!this.fields.length || previous === current) { return; }
    let start = 0;
    while (start < previous.length && start < current.length && previous[start] === current[start]) {
      start++;
    }
    let oldEnd = previous.length;
    let newEnd = current.length;
    while (oldEnd > start && newEnd > start && previous[oldEnd - 1] === current[newEnd - 1]) {
      oldEnd--;
      newEnd--;
    }
    const offset = newEnd - oldEnd;
    const preserved = this.fields.flatMap(field => {
      if (field.end <= start) { return [field]; }
      if (field.start >= oldEnd) {
        return [{ ...field, start: field.start + offset, end: field.end + offset }];
      }
      return [];
    });
    if (preserved.length < this.fields.length) {
      this.fieldFeedback = 'Vuelve a marcar los campos cuyo texto cambiaste.';
    }
    this.fields = preserved;
  }
}
