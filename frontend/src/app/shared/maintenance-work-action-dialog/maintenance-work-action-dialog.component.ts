import { CommonModule } from '@angular/common';
import { Component, Inject } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MAT_DIALOG_DATA, MatDialogModule, MatDialogRef } from '@angular/material/dialog';
import { MatButtonModule } from '@angular/material/button';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatIconModule } from '@angular/material/icon';

export type MaintenanceWorkAction = 'complete' | 'return';

export interface MaintenanceWorkActionDialogData {
  ticketId: number;
  action: MaintenanceWorkAction;
}

@Component({
  selector: 'app-maintenance-work-action-dialog',
  standalone: true,
  imports: [
    CommonModule,
    FormsModule,
    MatDialogModule,
    MatButtonModule,
    MatFormFieldModule,
    MatInputModule,
    MatIconModule,
  ],
  templateUrl: './maintenance-work-action-dialog.component.html',
  styleUrls: ['./maintenance-work-action-dialog.component.css'],
})
export class MaintenanceWorkActionDialogComponent {
  notes = '';

  constructor(
    @Inject(MAT_DIALOG_DATA) public readonly data: MaintenanceWorkActionDialogData,
    private readonly dialogRef: MatDialogRef<MaintenanceWorkActionDialogComponent>,
  ) {}

  get isCompletion(): boolean {
    return this.data.action === 'complete';
  }

  get title(): string {
    return this.isCompletion ? 'Trabajo terminado' : 'Devolver al técnico';
  }

  get description(): string {
    return this.isCompletion
      ? 'Registra lo que reparaste. Yuliana revisará el trabajo antes de solicitar el cierre.'
      : 'Explica qué falta corregir. El ticket volverá al técnico asignado.';
  }

  get fieldLabel(): string {
    return this.isCompletion ? 'Trabajo realizado' : 'Motivo de devolución';
  }

  get maxLength(): number {
    return this.isCompletion ? 2000 : 500;
  }

  get canSubmit(): boolean {
    const length = this.notes.trim().length;
    return length > 0 && length <= this.maxLength;
  }

  save(): void {
    if (!this.canSubmit) return;
    this.dialogRef.close(this.notes.trim());
  }

  cancel(): void {
    this.dialogRef.close(null);
  }
}
