// frontend/src/app/planning/targets/planning-target-action-dialog/planning-target-action-dialog.component.ts

import { CommonModule } from '@angular/common';
import { Component, Inject } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MAT_DIALOG_DATA, MatDialogModule, MatDialogRef } from '@angular/material/dialog';
import { MatButtonModule } from '@angular/material/button';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';

export interface PlanningTargetActionDialogData {
  title: string;
  actionLabel: string;
  description: string;
  warning?: string;
  defaultComment?: string;
  requireComment?: boolean;
  confirmColor?: 'primary' | 'warn';
}

export interface PlanningTargetActionDialogResult {
  confirmed: boolean;
  comment: string;
}

@Component({
  selector: 'app-planning-target-action-dialog',
  standalone: true,
  imports: [
    CommonModule,
    FormsModule,
    MatButtonModule,
    MatDialogModule,
    MatFormFieldModule,
    MatIconModule,
    MatInputModule,
  ],
  templateUrl: './planning-target-action-dialog.component.html',
  styleUrls: ['./planning-target-action-dialog.component.css',]
})
export class PlanningTargetActionDialogComponent {
  comment = '';

  constructor(
    private readonly dialogRef: MatDialogRef<
      PlanningTargetActionDialogComponent,
      PlanningTargetActionDialogResult
    >,
    @Inject(MAT_DIALOG_DATA)
    public readonly data: PlanningTargetActionDialogData,
  ) {
    this.comment = data.defaultComment || '';
  }

  canConfirm(): boolean {
    if (!this.data.requireComment) {
      return true;
    }

    return this.comment.trim().length >= 5;
  }

  cancel(): void {
    this.dialogRef.close({
      confirmed: false,
      comment: '',
    });
  }

  confirm(): void {
    if (!this.canConfirm()) {
      return;
    }

    this.dialogRef.close({
      confirmed: true,
      comment: this.comment.trim(),
    });
  }

  getConfirmColor(): 'primary' | 'warn' {
    return this.data.confirmColor || 'primary';
  }
}