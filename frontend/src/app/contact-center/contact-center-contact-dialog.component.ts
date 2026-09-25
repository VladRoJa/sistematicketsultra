import { CommonModule } from '@angular/common';
import { Component, Inject, OnInit } from '@angular/core';
import { FormsModule } from '@angular/forms';
import {
  MAT_DIALOG_DATA,
  MatDialog,
  MatDialogModule,
  MatDialogRef,
} from '@angular/material/dialog';
import { MatIconModule } from '@angular/material/icon';

import {
  ContactCenterAccess,
  ContactCenterAppointment,
  ContactCenterBranch,
  ContactCenterCase,
  ContactCenterContact,
  ContactCenterContactDetail,
  ContactCenterInteractionOutcome,
  ContactCenterLookups,
} from './contact-center.models';
import {
  ContactCenterAppointmentDialogComponent,
} from './contact-center-appointment-dialog.component';
import {
  ContactCenterDuplicateDialogComponent,
} from './contact-center-duplicate-dialog.component';
import { ContactCenterService } from './contact-center.service';


export interface ContactCenterContactDialogData {
  contactId: number;
  access: ContactCenterAccess;
  lookups: ContactCenterLookups;
}

export interface ContactCenterContactDialogResult {
  changed: boolean;
  contactId: number;
}


@Component({
  selector: 'app-contact-center-contact-dialog',
  standalone: true,
  imports: [
    CommonModule,
    FormsModule,
    MatDialogModule,
    MatIconModule,
  ],
  templateUrl: './contact-center-contact-dialog.component.html',
  styleUrls: ['./contact-center-contact-dialog.component.css'],
})
export class ContactCenterContactDialogComponent implements OnInit {
  contact: ContactCenterContactDetail | null = null;
  contactId: number;

  loading = false;
  savingInteraction = false;
  savingAppointment = false;
  assigningCase = false;
  changed = false;

  interactionType: 'CALL' | 'MESSAGE' | 'NOTE' = 'CALL';
  interactionOutcome: ContactCenterInteractionOutcome = 'NO_ANSWER';
  interactionComment = '';
  interactionNextAction = '';

  appointmentBranchId: number | null = null;
  appointmentScheduledAt = '';
  appointmentNotes = '';

  selectedAssignedUserId: number | null = null;

  feedbackMessage = '';
  feedbackKind: 'SUCCESS' | 'ERROR' | 'INFO' = 'INFO';

  readonly interactionOptions: Array<{
    value: ContactCenterInteractionOutcome;
    label: string;
  }> = [
    { value: 'NO_ANSWER', label: 'No contestó' },
    { value: 'CALL_BACK', label: 'Volver a llamar' },
    { value: 'INTERESTED', label: 'Interesado' },
    { value: 'NOT_INTERESTED', label: 'No interesado' },
    { value: 'WRONG_NUMBER', label: 'Número incorrecto' },
    { value: 'DO_NOT_CONTACT', label: 'No contactar' },
    { value: 'NOTE', label: 'Sólo comentario' },
  ];

  constructor(
    @Inject(MAT_DIALOG_DATA)
    public readonly data: ContactCenterContactDialogData,
    private readonly dialogRef: MatDialogRef<
      ContactCenterContactDialogComponent,
      ContactCenterContactDialogResult
    >,
    private readonly dialog: MatDialog,
    private readonly contactCenter: ContactCenterService,
  ) {
    this.contactId = data.contactId;
  }

  ngOnInit(): void {
    this.loadContact();
  }

  get isSupervisor(): boolean {
    return Boolean(this.data.access.is_supervisor);
  }

  get isManager(): boolean {
    return Boolean(this.data.access.is_manager);
  }

  get activeCase(): ContactCenterCase | null {
    const activeCases = (
      this.contact?.cases.filter((row) => row.status !== 'CLOSED')
      ?? []
    );

    const currentUserId = this.data.access.user.id;
    const ownCase = activeCases.find(
      (row) => row.assigned_user?.id === currentUserId,
    );

    return ownCase ?? activeCases[0] ?? null;
  }

  get displayCase(): ContactCenterCase | null {
    return this.activeCase ?? this.contact?.cases[0] ?? null;
  }

  get canOperateActiveCase(): boolean {
    if (this.isSupervisor) {
      return true;
    }

    return Boolean(
      this.activeCase
      && this.activeCase.assigned_user?.id === this.data.access.user.id
    );
  }

  get needsFollowUpDate(): boolean {
    return this.interactionOutcome === 'CALL_BACK';
  }

  get activeScheduledAppointment(): ContactCenterAppointment | null {
    return (
      this.contact?.appointments.find((row) => row.status === 'SCHEDULED')
      ?? null
    );
  }

  get activeAppointmentHelpText(): string {
    return this.isManager
      ? 'Registra el resultado cuando la cita sea atendida.'
      : 'Este caso ya tiene una cita activa. Para cambiarla usa Reagendar.';
  }

  get purchaseAppointment(): ContactCenterAppointment | null {
    const appointments = this.contact?.appointments ?? [];

    return (
      appointments.find(
        (row) => row.purchase_verification_status === 'VERIFIED',
      )
      ?? appointments.find((row) => row.purchase_reported)
      ?? null
    );
  }

  close(): void {
    this.dialogRef.close({
      changed: this.changed,
      contactId: this.contactId,
    });
  }

  submitInteraction(): void {
    const currentCase = this.activeCase;
    if (!currentCase) {
      this.showFeedback('Este contacto no tiene un caso activo.', 'ERROR');
      return;
    }

    if (this.needsFollowUpDate && !this.interactionNextAction) {
      this.showFeedback(
        'Indica cuándo hay que volver a llamar.',
        'ERROR',
      );
      return;
    }

    this.savingInteraction = true;
    this.contactCenter.addInteraction(currentCase.id, {
      interaction_type: this.interactionType,
      outcome: this.interactionOutcome,
      comment: this.interactionComment.trim() || null,
      next_action_at: this.needsFollowUpDate
        ? this.interactionNextAction
        : null,
    }).subscribe({
      next: () => {
        this.savingInteraction = false;
        this.changed = true;
        this.resetInteraction();
        this.loadContact();
        this.showFeedback('Seguimiento guardado.', 'SUCCESS');
      },
      error: (error) => {
        this.savingInteraction = false;
        this.showApiError(error, 'No se pudo guardar el seguimiento.');
      },
    });
  }

  scheduleAppointment(): void {
    const currentCase = this.activeCase;
    if (!currentCase) {
      this.showFeedback('Este contacto no tiene un caso activo.', 'ERROR');
      return;
    }

    if (this.activeScheduledAppointment) {
      this.showFeedback(
        'Este caso ya tiene una cita programada. Usa Gestionar cita para reagendarla.',
        'ERROR',
      );
      return;
    }

    if (!this.appointmentBranchId || !this.appointmentScheduledAt) {
      this.showFeedback(
        'Selecciona sucursal, fecha y hora para la cita.',
        'ERROR',
      );
      return;
    }

    this.savingAppointment = true;
    this.contactCenter.createAppointment(currentCase.id, {
      sucursal_id: this.appointmentBranchId,
      scheduled_at: this.appointmentScheduledAt,
      notes: this.appointmentNotes.trim() || null,
    }).subscribe({
      next: (response) => {
        this.savingAppointment = false;
        this.changed = true;
        this.appointmentScheduledAt = '';
        this.appointmentNotes = '';
        this.loadContact();

        const message = this.isManager
          ? 'Cita creada y agregada a tu agenda.'
          : response.notification.queued
            ? 'Cita creada. La notificación por correo quedó en proceso.'
            : 'Cita creada. No se encontró correo de gerente para notificar.';

        this.showFeedback(message, 'SUCCESS');
      },
      error: (error) => {
        this.savingAppointment = false;
        this.showApiError(error, 'No se pudo crear la cita.');
      },
    });
  }

  assignActiveCase(): void {
    const currentCase = this.activeCase;
    if (
      !this.isSupervisor
      || !currentCase
      || !this.selectedAssignedUserId
    ) {
      return;
    }

    this.assigningCase = true;
    this.contactCenter.assignCase(
      currentCase.id,
      this.selectedAssignedUserId,
    ).subscribe({
      next: () => {
        this.assigningCase = false;
        this.changed = true;
        this.loadContact();
        this.showFeedback('Caso reasignado.', 'SUCCESS');
      },
      error: (error) => {
        this.assigningCase = false;
        this.showApiError(error, 'No se pudo reasignar el caso.');
      },
    });
  }

  reviewDuplicates(): void {
    const contact = this.contact;
    if (!contact) {
      return;
    }

    this.contactCenter.findDuplicates({
      phone: contact.phone_mx10 || contact.primary_phone_raw,
      email: contact.email,
      exclude_contact_id: contact.id,
    }).subscribe({
      next: (response) => {
        if (!response.rows.length) {
          this.showFeedback(
            'No se encontraron posibles duplicados.',
            'INFO',
          );
          return;
        }

        const ref = this.dialog.open(
          ContactCenterDuplicateDialogComponent,
          {
            maxWidth: '96vw',
            data: {
              baseContact: contact,
              candidates: response.rows,
              canMerge: this.isSupervisor,
            },
          },
        );

        ref.afterClosed().subscribe((result) => {
          if (!result?.contactId) {
            return;
          }

          this.changed = Boolean(result.merged) || this.changed;
          this.contactId = Number(result.contactId);
          this.loadContact();

          if (result.merged) {
            this.showFeedback(
              'Contactos unificados sin perder historial.',
              'SUCCESS',
            );
          }
        });
      },
      error: (error) => {
        this.showApiError(
          error,
          'No se pudo revisar posibles duplicados.',
        );
      },
    });
  }

  manageActiveAppointment(): void {
    const appointment = this.activeScheduledAppointment;
    if (!appointment || !this.canOperateActiveCase) {
      return;
    }

    const ref = this.dialog.open(
      ContactCenterAppointmentDialogComponent,
      {
        maxWidth: '96vw',
        data: {
          appointment,
          branches: this.data.lookups.branches,
          canReschedule: !this.isManager,
        },
      },
    );

    ref.afterClosed().subscribe((result) => {
      if (!result?.action) {
        return;
      }

      if (result.action === 'RESCHEDULE') {
        this.rescheduleAppointment(appointment, result);
        return;
      }

      this.closeAppointment(appointment, result);
    });
  }

  sourceLabel(source: string | null | undefined): string {
    const labels: Record<string, string> = {
      CRM: 'CRM',
      MESSAGE: 'Mensaje',
      REACTIVATION: 'Reactivación',
      CAMPAIGN: 'Campaña',
      MANUAL: 'Manual',
    };
    return labels[String(source || '')] || String(source || '—');
  }

  caseStatusLabel(status: string | null | undefined): string {
    const labels: Record<string, string> = {
      NEW: 'Nuevo',
      IN_PROGRESS: 'En seguimiento',
      FOLLOW_UP: 'Volver a llamar',
      APPOINTMENT: 'Con cita',
      CLOSED: 'Cerrado',
    };
    return labels[String(status || '')] || String(status || '—');
  }

  interactionLabel(outcome: string): string {
    const labels: Record<string, string> = {
      NO_ANSWER: 'No contestó',
      CALL_BACK: 'Volver a llamar',
      INTERESTED: 'Interesado',
      APPOINTMENT: 'Cita generada',
      NOT_INTERESTED: 'No interesado',
      WRONG_NUMBER: 'Número incorrecto',
      DO_NOT_CONTACT: 'No contactar',
      NOTE: 'Comentario',
    };
    return labels[outcome] || outcome;
  }

  appointmentStatusLabel(row: ContactCenterAppointment): string {
    if (row.closure_pending) {
      return 'Cierre pendiente';
    }

    const labels: Record<string, string> = {
      SCHEDULED: 'Programada',
      CLOSED: 'Cerrada',
      CANCELLED: 'Cancelada',
      RESCHEDULED: 'Reagendada',
    };
    return labels[row.status] || row.status;
  }

  purchaseLabel(row: ContactCenterAppointment | null): string {
    if (!row) {
      return 'Sin compra';
    }

    const labels: Record<string, string> = {
      NOT_REPORTED: 'Sin compra reportada',
      REPORTED_PENDING: 'Compra reportada · pendiente',
      NOT_FOUND_YET: 'Compra reportada · aún no encontrada',
      REVIEW: 'Compra · revisar coincidencia',
      VERIFIED: 'Compra validada',
    };

    return labels[row.purchase_verification_status]
      || row.purchase_verification_status;
  }

  purchaseClass(row: ContactCenterAppointment | null): string {
    if (row?.purchase_verification_status === 'VERIFIED') {
      return 'verified';
    }
    if (row?.purchase_reported) {
      return 'pending';
    }
    return 'neutral';
  }

  contactName(contact: ContactCenterContact | null | undefined): string {
    return contact?.display_name || 'Sin nombre';
  }

  contactPhone(contact: ContactCenterContact | null | undefined): string {
    return (
      contact?.phone_mx10
      || contact?.primary_phone_raw
      || 'Sin teléfono'
    );
  }

  branchName(branch: ContactCenterBranch | null | undefined): string {
    return branch?.name || 'Sin sucursal';
  }

  formatDateTime(value: string | null | undefined): string {
    if (!value) {
      return '—';
    }

    const parsed = new Date(value);
    if (Number.isNaN(parsed.getTime())) {
      return value;
    }

    return new Intl.DateTimeFormat('es-MX', {
      timeZone: 'America/Tijuana',
      dateStyle: 'medium',
      timeStyle: 'short',
    }).format(parsed);
  }

  private loadContact(): void {
    this.loading = true;
    this.contactCenter.getContact(this.contactId).subscribe({
      next: (detail) => {
        this.contact = detail;
        this.loading = false;

        const currentCase = this.activeCase;
        this.selectedAssignedUserId =
          currentCase?.assigned_user?.id ?? null;
        this.appointmentBranchId =
          currentCase?.sucursal?.id
          ?? detail.preferred_sucursal?.id
          ?? null;
      },
      error: (error) => {
        this.loading = false;
        this.showApiError(error, 'No se pudo abrir el contacto.');
      },
    });
  }

  private closeAppointment(
    appointment: ContactCenterAppointment,
    result: {
      outcome: 'ATTENDED_PURCHASE_REPORTED'
        | 'ATTENDED_NO_PURCHASE'
        | 'NO_SHOW'
        | 'CANCELLED';
      notes?: string | null;
    },
  ): void {
    this.contactCenter.closeAppointment(
      appointment.id,
      {
        outcome: result.outcome,
        notes: result.notes,
      },
    ).subscribe({
      next: () => {
        this.changed = true;
        this.loadContact();
        this.showFeedback('Cita cerrada.', 'SUCCESS');
      },
      error: (error) => {
        this.showApiError(error, 'No se pudo cerrar la cita.');
      },
    });
  }

  private rescheduleAppointment(
    appointment: ContactCenterAppointment,
    result: {
      scheduled_at: string;
      sucursal_id: number;
      notes?: string | null;
    },
  ): void {
    this.contactCenter.rescheduleAppointment(
      appointment.id,
      {
        scheduled_at: result.scheduled_at,
        sucursal_id: result.sucursal_id,
        notes: result.notes,
      },
    ).subscribe({
      next: () => {
        this.changed = true;
        this.loadContact();
        this.showFeedback(
          'Cita reagendada y nueva notificación preparada.',
          'SUCCESS',
        );
      },
      error: (error) => {
        this.showApiError(error, 'No se pudo reagendar la cita.');
      },
    });
  }

  private resetInteraction(): void {
    this.interactionType = 'CALL';
    this.interactionOutcome = 'NO_ANSWER';
    this.interactionComment = '';
    this.interactionNextAction = '';
  }

  private showApiError(error: any, fallback: string): void {
    this.showFeedback(
      error?.error?.mensaje || fallback,
      'ERROR',
    );
  }

  private showFeedback(
    message: string,
    kind: 'SUCCESS' | 'ERROR' | 'INFO',
  ): void {
    this.feedbackMessage = message;
    this.feedbackKind = kind;
  }
}
