import { CommonModule } from '@angular/common';
import { Component, Inject } from '@angular/core';
import { MAT_DIALOG_DATA, MatDialogModule, MatDialogRef } from '@angular/material/dialog';
import { TimelineObservation } from './automation-control.models';
import { MatDialog } from '@angular/material/dialog';
import { AutomationErrorDetailDialogComponent, AutomationErrorDialogData } from './automation-error-detail-dialog.component';

export interface AutomationObservationDialogData {
  jobLabel: string;
  jobKey: string;
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
    private readonly dialog: MatDialog,
  ) {}

  openDiagnostic(): void {
    const data:AutomationErrorDialogData = {
      jobKey:this.data.jobKey,jobLabel:this.data.jobLabel,
      runId:this.data.observation.run_id,
    };
    this.dialog.open(AutomationErrorDetailDialogComponent,{
      data,width:'min(610px,96vw)',maxWidth:'96vw',autoFocus:false,
    });
  }
  canDiagnose(): boolean {
    return ['FAILED','ERROR','TIMED_OUT','PARTIAL'].includes(
      this.data.observation.status_raw.toUpperCase()
    );
  }
  close(): void { this.dialogRef.close(); }

  formatDate(value: string | null): string {
    if (!value) { return 'Sin registro'; }
    const parsed = new Date(value);
    return Number.isNaN(parsed.getTime())
      ? 'Fecha no disponible'
      : parsed.toLocaleString('es-MX', { timeZone: 'America/Tijuana' });
  }
}
