import { CommonModule } from '@angular/common';
import { Component, Inject } from '@angular/core';
import { MAT_DIALOG_DATA, MatDialogModule, MatDialogRef } from '@angular/material/dialog';
import { TimelineObservation } from './automation-control.models';

export interface AutomationObservationDialogData {
  jobLabel: string;
  observation: TimelineObservation;
}

@Component({
  selector: 'app-automation-observation-dialog',
  standalone: true,
  imports: [CommonModule, MatDialogModule],
  templateUrl: './automation-observation-dialog.component.html',
  styleUrls: ['./automation-observation-dialog.component.css'],
})
export class AutomationObservationDialogComponent {
  constructor(
    @Inject(MAT_DIALOG_DATA) public readonly data: AutomationObservationDialogData,
    private readonly dialogRef: MatDialogRef<AutomationObservationDialogComponent>,
  ) {}

  close(): void { this.dialogRef.close(); }

  formatDate(value: string | null): string {
    if (!value) { return 'Sin registro'; }
    const parsed = new Date(value);
    return Number.isNaN(parsed.getTime())
      ? 'Fecha no disponible'
      : parsed.toLocaleString('es-MX', { timeZone: 'America/Tijuana' });
  }
}
