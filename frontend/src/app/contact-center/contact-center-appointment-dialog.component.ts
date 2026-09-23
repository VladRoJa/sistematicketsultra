import { CommonModule } from '@angular/common';
import { Component, Inject } from '@angular/core';
import { FormsModule } from '@angular/forms';
import {
  MAT_DIALOG_DATA,
  MatDialogModule,
  MatDialogRef,
} from '@angular/material/dialog';
import { MatIconModule } from '@angular/material/icon';

import {
  ContactCenterAppointment,
  ContactCenterAppointmentOutcome,
  ContactCenterBranch,
} from './contact-center.models';


export interface ContactCenterAppointmentDialogData {
  appointment: ContactCenterAppointment;
  branches: ContactCenterBranch[];
}


type AppointmentAction = 'CLOSE' | 'RESCHEDULE';


@Component({
  selector: 'app-contact-center-appointment-dialog',
  standalone: true,
  imports: [
    CommonModule,
    FormsModule,
    MatDialogModule,
    MatIconModule,
  ],
  templateUrl: './contact-center-appointment-dialog.component.html',
  styleUrls: ['./contact-center-appointment-dialog.component.css'],
})
export class ContactCenterAppointmentDialogComponent {
  action: AppointmentAction = 'CLOSE';
  outcome: Exclude<ContactCenterAppointmentOutcome, 'RESCHEDULED'> =
    'ATTENDED_NO_PURCHASE';
  notes = '';
  scheduledAt = '';
  sucursalId: number;

  readonly outcomes: Array<{
    value: Exclude<ContactCenterAppointmentOutcome, 'RESCHEDULED'>;
    label: string;
  }> = [
    {
      value: 'ATTENDED_PURCHASE_REPORTED',
      label: 'Asistió y compró',
    },
    {
      value: 'ATTENDED_NO_PURCHASE',
      label: 'Asistió y no compró',
    },
    {
      value: 'NO_SHOW',
      label: 'No asistió',
    },
    {
      value: 'CANCELLED',
      label: 'Cancelada',
    },
  ];

  constructor(
    @Inject(MAT_DIALOG_DATA)
    public readonly data: ContactCenterAppointmentDialogData,
    private readonly dialogRef: MatDialogRef<ContactCenterAppointmentDialogComponent>,
  ) {
    this.sucursalId = data.appointment.sucursal?.id ?? 0;
  }

  submit(): void {
    if (this.action === 'RESCHEDULE') {
      if (!this.scheduledAt || !this.sucursalId) {
        return;
      }

      this.dialogRef.close({
        action: 'RESCHEDULE',
        scheduled_at: this.scheduledAt,
        sucursal_id: this.sucursalId,
        notes: this.notes.trim() || null,
      });
      return;
    }

    this.dialogRef.close({
      action: 'CLOSE',
      outcome: this.outcome,
      notes: this.notes.trim() || null,
    });
  }

  close(): void {
    this.dialogRef.close();
  }

  submitLabel(): string {
    return this.action === 'RESCHEDULE'
      ? 'Reagendar cita'
      : 'Guardar cierre';
  }

  canSubmit(): boolean {
    if (this.action === 'RESCHEDULE') {
      return Boolean(this.scheduledAt && this.sucursalId);
    }
    return Boolean(this.outcome);
  }
}
