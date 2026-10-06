import { CommonModule } from '@angular/common';
import { Component, Inject } from '@angular/core';
import {
  UntypedFormArray,
  UntypedFormBuilder,
  UntypedFormGroup,
  ReactiveFormsModule,
  Validators,
} from '@angular/forms';
import {
  MAT_DIALOG_DATA,
  MatDialogModule,
  MatDialogRef,
} from '@angular/material/dialog';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatSelectModule } from '@angular/material/select';
import { finalize } from 'rxjs';

import {
  CreatePurchaseRequisitionPayload,
  PurchaseRequisition,
  PurchaseRequisitionService,
} from './purchase-requisition.service';

export interface PurchaseRequisitionBranchOption {
  id: number;
  name: string;
}

export interface PurchaseRequisitionFormDialogData {
  branches: PurchaseRequisitionBranchOption[];
  requisition?: PurchaseRequisition | null;
}

@Component({
  selector: 'app-purchase-requisition-form-dialog',
  standalone: true,
  templateUrl: './purchase-requisition-form-dialog.component.html',
  styleUrls: ['./purchase-requisition-form-dialog.component.css'],
  imports: [
    CommonModule,
    ReactiveFormsModule,
    MatButtonModule,
    MatDialogModule,
    MatIconModule,
    MatFormFieldModule,
    MatInputModule,
    MatSelectModule,
  ],
})
export class PurchaseRequisitionFormDialogComponent {
  readonly reasons = [
    { value: 'REPLACEMENT', label: 'Reemplazo' },
    { value: 'NEW_EQUIPMENT', label: 'Equipo nuevo' },
    { value: 'DAMAGE', label: 'Daño' },
    { value: 'EXPANSION', label: 'Expansión' },
    { value: 'OTHER', label: 'Otro' },
  ];

  readonly priorities = [
    { value: 'NORMAL', label: 'Normal' },
    { value: 'HIGH', label: 'Alta' },
    { value: 'CRITICAL', label: 'Crítica' },
  ];

  readonly form: UntypedFormGroup;
  readonly isEditMode: boolean;
  saving = false;
  errorMessage = '';

  constructor(
    private readonly fb: UntypedFormBuilder,
    private readonly requisitionService: PurchaseRequisitionService,
    private readonly dialogRef: MatDialogRef<PurchaseRequisitionFormDialogComponent>,
    @Inject(MAT_DIALOG_DATA)
    readonly data: PurchaseRequisitionFormDialogData,
  ) {
    this.isEditMode = Boolean(data.requisition);
    const requisition = data.requisition;

    this.form = this.fb.group({
      sucursal_id: [
        requisition?.sucursal_id
          ?? (data.branches.length === 1 ? data.branches[0].id : null),
        [Validators.required],
      ],
      reason: [requisition?.reason ?? 'REPLACEMENT', [Validators.required]],
      priority: [requisition?.priority ?? 'NORMAL', [Validators.required]],
      justification: [requisition?.justification ?? '', [Validators.required]],
      items: this.fb.array([]),
    });

    const initialItems = requisition?.items?.length
      ? requisition.items
      : [null];

    initialItems.forEach((item) => {
      this.items.push(this.createItemGroup(item));
    });

    if (this.isEditMode) {
      this.form.get('sucursal_id')?.disable();
    }
  }

  get title(): string {
    return this.isEditMode ? 'Corregir requisición' : 'Nueva requisición';
  }

  get submitLabel(): string {
    return this.isEditMode ? 'Guardar correcciones' : 'Enviar a revisión';
  }

  get items(): UntypedFormArray {
    return this.form.get('items') as UntypedFormArray;
  }

  addItem(): void {
    this.items.push(this.createItemGroup());
  }

  removeItem(index: number): void {
    if (this.items.length <= 1) {
      return;
    }
    this.items.removeAt(index);
  }

  submit(): void {
    this.errorMessage = '';

    if (this.form.invalid) {
      this.form.markAllAsTouched();
      return;
    }

    const raw = this.form.getRawValue();
    const items = (raw.items || []).map((item: any) => ({
      item_description: String(item.item_description || '').trim(),
      quantity: Number(item.quantity),
      notes: String(item.notes || '').trim() || null,
    }));

    this.saving = true;

    const request$ = this.isEditMode && this.data.requisition
      ? this.requisitionService.requesterEdit(
          this.data.requisition.id,
          {
            reason: String(raw.reason),
            priority: raw.priority,
            justification: String(raw.justification || '').trim(),
            items,
          },
        )
      : this.requisitionService.create({
          sucursal_id: Number(raw.sucursal_id),
          category: 'GYM_EQUIPMENT',
          reason: String(raw.reason),
          priority: raw.priority,
          justification: String(raw.justification || '').trim(),
          items,
        } as CreatePurchaseRequisitionPayload);

    request$
      .pipe(finalize(() => {
        this.saving = false;
      }))
      .subscribe({
        next: (response) => {
          this.dialogRef.close(response.requisition);
        },
        error: (error) => {
          this.errorMessage = String(
            error?.error?.mensaje
            || (
              this.isEditMode
                ? 'No fue posible guardar las correcciones.'
                : 'No fue posible crear la requisición.'
            ),
          );
        },
      });
  }

  private createItemGroup(item?: any): UntypedFormGroup {
    return this.fb.group({
      item_description: [
        item?.item_description ?? '',
        [Validators.required],
      ],
      quantity: [
        item?.quantity ?? 1,
        [Validators.required, Validators.min(1)],
      ],
      notes: [item?.notes ?? ''],
    });
  }
}
