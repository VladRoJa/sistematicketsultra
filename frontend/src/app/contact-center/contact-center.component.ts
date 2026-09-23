import { CommonModule } from '@angular/common';
import { Component, OnInit } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatDialog, MatDialogModule } from '@angular/material/dialog';
import { MatIconModule } from '@angular/material/icon';

import {
  ContactCenterAccess,
  ContactCenterAppointment,
  ContactCenterBranch,
  ContactCenterCalendarCell,
  ContactCenterCase,
  ContactCenterContact,
  ContactCenterContactDetail,
  ContactCenterCrmCandidate,
  ContactCenterInteractionOutcome,
  ContactCenterLookups,
  ContactCenterReportSummary,
  ContactCenterSource,
} from './contact-center.models';
import {
  ContactCenterAppointmentDialogComponent,
} from './contact-center-appointment-dialog.component';
import {
  ContactCenterDuplicateDialogComponent,
} from './contact-center-duplicate-dialog.component';
import {
  ContactCenterNewContactDialogComponent,
} from './contact-center-new-contact-dialog.component';
import { ContactCenterService } from './contact-center.service';


type ContactCenterTab = 'PORTFOLIO' | 'CRM' | 'APPOINTMENTS';
type AppointmentView = 'TABLE' | 'CALENDAR';


@Component({
  selector: 'app-contact-center',
  standalone: true,
  imports: [
    CommonModule,
    FormsModule,
    MatDialogModule,
    MatIconModule,
  ],
  templateUrl: './contact-center.component.html',
  styleUrls: ['./contact-center.component.css'],
})
export class ContactCenterComponent implements OnInit {
  access: ContactCenterAccess | null = null;
  lookups: ContactCenterLookups = {
    branches: [],
    agents: [],
  };

  activeTab: ContactCenterTab = 'PORTFOLIO';
  appointmentView: AppointmentView = 'TABLE';

  contacts: ContactCenterContact[] = [];
  selectedContact: ContactCenterContactDetail | null = null;
  crmCandidates: ContactCenterCrmCandidate[] = [];
  appointments: ContactCenterAppointment[] = [];
  calendarCells: ContactCenterCalendarCell[] = [];

  reportSummary: ContactCenterReportSummary = {
    active_cases: 0,
    new: 0,
    in_progress: 0,
    follow_up: 0,
    appointment_cases: 0,
    appointments: 0,
    closure_pending: 0,
    purchase_reported: 0,
    purchase_verified: 0,
  };

  loadingPortfolio = false;
  loadingDetail = false;
  loadingCrm = false;
  loadingAppointments = false;
  savingInteraction = false;
  savingAppointment = false;
  assigningCase = false;

  searchText = '';
  statusFilter = '';
  sourceFilter = '';

  interactionType: 'CALL' | 'MESSAGE' | 'NOTE' = 'CALL';
  interactionOutcome: ContactCenterInteractionOutcome = 'NO_ANSWER';
  interactionComment = '';
  interactionNextAction = '';

  appointmentBranchId: number | null = null;
  appointmentScheduledAt = '';
  appointmentNotes = '';

  selectedAssignedUserId: number | null = null;

  crmMonth = this.currentBusinessMonth();
  crmPhoneSearch = '';
  crmSearchMode: 'MONTH' | 'PHONE' = 'MONTH';
  calendarCursor = this.firstDayOfBusinessMonth();

  feedbackMessage = '';
  feedbackKind: 'SUCCESS' | 'ERROR' | 'INFO' = 'INFO';

  readonly sourceOptions: Array<{
    value: ContactCenterSource;
    label: string;
  }> = [
    { value: 'CRM', label: 'CRM' },
    { value: 'MESSAGE', label: 'Mensaje' },
    { value: 'REACTIVATION', label: 'Reactivación' },
    { value: 'CAMPAIGN', label: 'Campaña' },
    { value: 'MANUAL', label: 'Manual' },
  ];

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

  readonly weekDays = ['Lun', 'Mar', 'Mié', 'Jue', 'Vie', 'Sáb', 'Dom'];

  constructor(
    private readonly contactCenter: ContactCenterService,
    private readonly dialog: MatDialog,
  ) {}

  ngOnInit(): void {
    this.loadAccess();
  }

  get isSupervisor(): boolean {
    return Boolean(this.access?.is_supervisor);
  }

  get isManager(): boolean {
    return Boolean(this.access?.is_manager);
  }

  get activeCase(): ContactCenterCase | null {
    return (
      this.selectedContact?.cases.find((row) => row.status !== 'CLOSED')
      ?? null
    );
  }

  get needsFollowUpDate(): boolean {
    return this.interactionOutcome === 'CALL_BACK';
  }

  get activeScheduledAppointment(): ContactCenterAppointment | null {
    return (
      this.selectedContact?.appointments.find(
        (row) => row.status === 'SCHEDULED',
      )
      ?? null
    );
  }

  setTab(tab: ContactCenterTab): void {
    if (this.isManager && tab !== 'APPOINTMENTS') {
      return;
    }

    this.activeTab = tab;
    this.clearFeedback();

    if (tab === 'CRM' && !this.crmCandidates.length) {
      this.loadCrmCandidates();
    }

    if (tab === 'APPOINTMENTS') {
      this.loadAppointments();
    }
  }

  openNewContact(): void {
    if (!this.access || this.isManager) {
      return;
    }

    const ref = this.dialog.open(
      ContactCenterNewContactDialogComponent,
      {
        maxWidth: '96vw',
        data: {
          branches: this.lookups.branches,
          agents: this.lookups.agents,
          isSupervisor: this.isSupervisor,
          currentUserId: this.access.user.id,
        },
      },
    );

    ref.afterClosed().subscribe((result) => {
      if (!result?.contactId) {
        return;
      }

      this.loadPortfolio();
      this.openContact(Number(result.contactId));
      this.showFeedback(
        result.created
          ? 'Contacto creado y agregado a la cartera.'
          : 'Se abrió el contacto existente.',
        'SUCCESS',
      );
    });
  }

  loadPortfolio(): void {
    this.loadingPortfolio = true;

    this.contactCenter.getContacts({
      status: this.statusFilter || undefined,
      source_type: this.sourceFilter || undefined,
      q: this.searchText.trim() || undefined,
    }).subscribe({
      next: (response) => {
        this.contacts = response.rows;
        this.loadingPortfolio = false;
      },
      error: (error) => {
        this.loadingPortfolio = false;
        this.showApiError(error, 'No se pudo cargar la cartera.');
      },
    });
  }

  clearPortfolioFilters(): void {
    this.searchText = '';
    this.statusFilter = '';
    this.sourceFilter = '';
    this.loadPortfolio();
  }

  openContact(contactId: number): void {
    this.loadingDetail = true;

    this.contactCenter.getContact(contactId).subscribe({
      next: (detail) => {
        this.selectedContact = detail;
        this.loadingDetail = false;
        this.resetContactActions();

        const currentCase = detail.cases.find(
          (row) => row.status !== 'CLOSED',
        );
        this.selectedAssignedUserId =
          currentCase?.assigned_user?.id ?? null;
        this.appointmentBranchId =
          currentCase?.sucursal?.id
          ?? detail.preferred_sucursal?.id
          ?? null;
      },
      error: (error) => {
        this.loadingDetail = false;
        this.showApiError(error, 'No se pudo abrir el contacto.');
      },
    });
  }

  closeContactDetail(): void {
    this.selectedContact = null;
    this.resetContactActions();
  }

  submitInteraction(): void {
    const currentCase = this.activeCase;
    if (!currentCase) {
      this.showFeedback(
        'Este contacto no tiene un caso activo.',
        'ERROR',
      );
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
        this.interactionComment = '';
        this.interactionNextAction = '';
        this.interactionOutcome = 'NO_ANSWER';
        this.refreshSelectedContact();
        this.loadPortfolio();
        this.loadReport();
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
      this.showFeedback(
        'Este contacto no tiene un caso activo.',
        'ERROR',
      );
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
        this.appointmentScheduledAt = '';
        this.appointmentNotes = '';
        this.refreshSelectedContact();
        this.loadPortfolio();
        this.loadAppointments();
        this.loadReport();

        const message = response.notification.queued
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
        this.refreshSelectedContact();
        this.loadPortfolio();
        this.showFeedback('Caso reasignado.', 'SUCCESS');
      },
      error: (error) => {
        this.assigningCase = false;
        this.showApiError(error, 'No se pudo reasignar el caso.');
      },
    });
  }

  reviewDuplicates(): void {
    const contact = this.selectedContact;
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

          this.loadPortfolio();
          this.openContact(Number(result.contactId));
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

  loadCrmCandidates(): void {
    this.crmSearchMode = 'MONTH';
    this.loadCrmCandidatesRequest();
  }

  searchCrmByPhone(): void {
    const phone = this.crmPhoneSearch.trim();
    if (!phone) {
      this.showFeedback(
        'Ingresa un teléfono para buscar en todo el histórico CRM.',
        'ERROR',
      );
      return;
    }

    this.crmSearchMode = 'PHONE';
    this.loadCrmCandidatesRequest(phone);
  }

  clearCrmPhoneSearch(): void {
    this.crmPhoneSearch = '';
    this.crmSearchMode = 'MONTH';
    this.loadCrmCandidates();
  }

  crmResultsDescription(): string {
    if (this.crmSearchMode === 'PHONE') {
      return (
        `${this.crmCandidates.length} coincidencia`
        + (this.crmCandidates.length === 1 ? '' : 's')
        + ' en todo el histórico CRM.'
      );
    }

    return `${this.crmCandidates.length} contactos disponibles en el corte.`;
  }

  importCrmCandidate(row: ContactCenterCrmCandidate): void {
    if (
      row.already_in_contact_center
      && row.has_active_case
      && row.contact_center_contact_id
    ) {
      this.activeTab = 'PORTFOLIO';
      this.openContact(row.contact_center_contact_id);
      return;
    }

    this.importCrmCandidateIntoContact(row, null);
  }

  crmActionLabel(row: ContactCenterCrmCandidate): string {
    if (row.already_in_contact_center && row.has_active_case) {
      return 'Abrir';
    }
    if (row.already_in_contact_center) {
      return 'Nuevo caso';
    }
    return 'Agregar';
  }

  loadAppointments(): void {
    const range = this.calendarRange();
    this.loadingAppointments = true;

    this.contactCenter.getAppointments({
      date_from: range.dateFrom,
      date_to: range.dateTo,
    }).subscribe({
      next: (response) => {
        this.appointments = response.rows;
        this.calendarCells = this.buildCalendarCells(
          this.calendarCursor,
          response.rows,
        );
        this.loadingAppointments = false;
        this.loadReport();
      },
      error: (error) => {
        this.loadingAppointments = false;
        this.showApiError(error, 'No se pudieron cargar las citas.');
      },
    });
  }

  setAppointmentView(view: AppointmentView): void {
    this.appointmentView = view;
  }

  moveCalendarMonth(delta: number): void {
    this.calendarCursor = new Date(
      Date.UTC(
        this.calendarCursor.getUTCFullYear(),
        this.calendarCursor.getUTCMonth() + delta,
        1,
      ),
    );
    this.loadAppointments();
  }

  manageActiveAppointment(): void {
    const appointment = this.activeScheduledAppointment;
    if (!appointment) {
      return;
    }

    this.appointmentAction(appointment);
  }

  appointmentAction(appointment: ContactCenterAppointment): void {
    const ref = this.dialog.open(
      ContactCenterAppointmentDialogComponent,
      {
        maxWidth: '96vw',
        data: {
          appointment,
          branches: this.lookups.branches,
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

  verifyPurchase(appointment: ContactCenterAppointment): void {
    this.contactCenter.verifyPurchase(appointment.id).subscribe({
      next: () => {
        this.loadAppointments();
        this.refreshSelectedContactIfMatches(appointment.contact_id);
        this.showFeedback(
          'Se volvió a revisar la compra contra Venta Total.',
          'SUCCESS',
        );
      },
      error: (error) => {
        this.showApiError(
          error,
          'No se pudo validar la compra.',
        );
      },
    });
  }

  openAppointmentContact(appointment: ContactCenterAppointment): void {
    if (this.isManager) {
      return;
    }

    this.activeTab = 'PORTFOLIO';
    this.openContact(appointment.contact_id);
  }

  sourceLabel(source: string | null | undefined): string {
    return this.sourceOptions.find((row) => row.value === source)?.label
      ?? source
      ?? '—';
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

  appointmentOutcomeLabel(outcome: string | null): string {
    if (!outcome) {
      return 'Pendiente';
    }

    const labels: Record<string, string> = {
      ATTENDED_PURCHASE_REPORTED: 'Asistió y compró',
      ATTENDED_NO_PURCHASE: 'Asistió sin compra',
      NO_SHOW: 'No asistió',
      CANCELLED: 'Cancelada',
      RESCHEDULED: 'Reagendada',
    };
    return labels[outcome] || outcome;
  }

  purchaseLabel(row: ContactCenterAppointment): string {
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

  purchaseClass(row: ContactCenterAppointment): string {
    if (row.purchase_verification_status === 'VERIFIED') {
      return 'verified';
    }
    if (row.purchase_reported) {
      return 'pending';
    }
    return 'neutral';
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

  formatTime(value: string): string {
    const parsed = new Date(value);
    if (Number.isNaN(parsed.getTime())) {
      return '—';
    }

    return new Intl.DateTimeFormat('es-MX', {
      timeZone: 'America/Tijuana',
      hour: '2-digit',
      minute: '2-digit',
    }).format(parsed);
  }

  calendarMonthLabel(): string {
    const value = new Intl.DateTimeFormat('es-MX', {
      timeZone: 'UTC',
      month: 'long',
      year: 'numeric',
    }).format(this.calendarCursor);

    return value.charAt(0).toUpperCase() + value.slice(1);
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

  private loadCrmCandidatesRequest(phone?: string): void {
    this.loadingCrm = true;
    this.contactCenter.getCrmCandidates(
      this.crmMonth,
      phone,
    ).subscribe({
      next: (response) => {
        this.crmCandidates = response.rows;
        this.loadingCrm = false;
      },
      error: (error) => {
        this.loadingCrm = false;
        this.showApiError(
          error,
          phone
            ? 'No se pudo buscar el teléfono en el histórico CRM.'
            : 'No se pudieron cargar los leads del CRM.',
        );
      },
    });
  }

  private loadAccess(): void {
    this.contactCenter.getAccess().subscribe({
      next: (access) => {
        this.access = access;
        if (access.is_manager) {
          this.activeTab = 'APPOINTMENTS';
        }
        this.loadLookups();
      },
      error: (error) => {
        this.showApiError(
          error,
          'No se pudo validar el acceso a Contact Center.',
        );
      },
    });
  }

  private loadLookups(): void {
    this.contactCenter.getLookups().subscribe({
      next: (lookups) => {
        this.lookups = lookups;
        if (!this.isManager) {
          this.loadPortfolio();
        }
        this.loadAppointments();
      },
      error: (error) => {
        this.showApiError(
          error,
          'No se pudieron cargar los catálogos del módulo.',
        );
      },
    });
  }

  private loadReport(): void {
    const range = this.calendarRange();
    this.contactCenter.getReport({
      date_from: range.dateFrom,
      date_to: range.dateTo,
    }).subscribe({
      next: (report) => {
        this.reportSummary = report.summary;
      },
      error: () => {
        // El reporte no bloquea la operación principal.
      },
    });
  }

  private refreshSelectedContact(): void {
    if (!this.selectedContact) {
      return;
    }
    this.openContact(this.selectedContact.id);
  }

  private refreshSelectedContactIfMatches(contactId: number): void {
    if (this.selectedContact?.id === contactId) {
      this.openContact(contactId);
    }
  }

  private resetContactActions(): void {
    this.interactionType = 'CALL';
    this.interactionOutcome = 'NO_ANSWER';
    this.interactionComment = '';
    this.interactionNextAction = '';
    this.appointmentScheduledAt = '';
    this.appointmentNotes = '';
  }

  private importCrmCandidateIntoContact(
    row: ContactCenterCrmCandidate,
    targetContactId: number | null,
  ): void {
    this.contactCenter.importCrmCandidate(
      row.contact_row_id,
      targetContactId,
    ).subscribe({
      next: (response) => {
        row.already_in_contact_center = true;
        row.contact_center_contact_id = response.contact.id;
        row.has_active_case = true;
        this.loadPortfolio();
        this.activeTab = 'PORTFOLIO';
        this.openContact(response.contact.id);
        this.showFeedback(
          targetContactId
            ? 'Lead vinculado al contacto existente y caso listo para seguimiento.'
            : 'Lead agregado a la cartera de Contact Center.',
          'SUCCESS',
        );
      },
      error: (error) => {
        if (
          error?.status === 409
          && Array.isArray(error?.error?.duplicates)
          && error.error.duplicates.length
        ) {
          this.openCrmDuplicateReview(
            row,
            error.error.duplicates,
          );
          return;
        }

        this.showApiError(
          error,
          'No se pudo agregar el lead a la cartera.',
        );
      },
    });
  }

  private openCrmDuplicateReview(
    row: ContactCenterCrmCandidate,
    duplicates: ContactCenterContact[],
  ): void {
    if (!duplicates.length) {
      return;
    }

    const branch = this.lookups.branches.find(
      (item) => item.id === row.sucursal_id,
    ) ?? null;

    const crmContact: ContactCenterContact = {
      id: 0,
      display_name: row.name,
      primary_phone_raw: row.phone || '',
      phone_mx10: row.phone,
      email: null,
      preferred_sucursal: branch,
      is_active: true,
      merged_into_contact_id: null,
      created_at: row.first_message_at_local || '',
      updated_at: row.first_message_at_local || '',
    };

    const ref = this.dialog.open(
      ContactCenterDuplicateDialogComponent,
      {
        maxWidth: '96vw',
        data: {
          baseContact: crmContact,
          candidates: duplicates,
          canMerge: false,
        },
      },
    );

    ref.afterClosed().subscribe((result) => {
      if (!result?.contactId) {
        return;
      }

      this.importCrmCandidateIntoContact(
        row,
        Number(result.contactId),
      );
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
        this.loadAppointments();
        if (!this.isManager) {
          this.loadPortfolio();
          this.refreshSelectedContactIfMatches(appointment.contact_id);
        }
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
        this.loadAppointments();
        if (!this.isManager) {
          this.loadPortfolio();
          this.refreshSelectedContactIfMatches(appointment.contact_id);
        }
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

  private calendarRange(): {
    dateFrom: string;
    dateTo: string;
  } {
    const year = this.calendarCursor.getUTCFullYear();
    const month = this.calendarCursor.getUTCMonth();
    const lastDay = new Date(Date.UTC(year, month + 1, 0)).getUTCDate();

    return {
      dateFrom: this.dateKey(year, month + 1, 1),
      dateTo: this.dateKey(year, month + 1, lastDay),
    };
  }

  private buildCalendarCells(
    cursor: Date,
    appointments: ContactCenterAppointment[],
  ): ContactCenterCalendarCell[] {
    const year = cursor.getUTCFullYear();
    const month = cursor.getUTCMonth();
    const first = new Date(Date.UTC(year, month, 1));
    const mondayOffset = (first.getUTCDay() + 6) % 7;
    const start = new Date(
      Date.UTC(year, month, 1 - mondayOffset),
    );

    const byDate = new Map<string, ContactCenterAppointment[]>();
    for (const appointment of appointments) {
      const key = this.businessDateKey(appointment.scheduled_at);
      const bucket = byDate.get(key) ?? [];
      bucket.push(appointment);
      byDate.set(key, bucket);
    }

    const cells: ContactCenterCalendarCell[] = [];
    for (let index = 0; index < 42; index += 1) {
      const day = new Date(
        Date.UTC(
          start.getUTCFullYear(),
          start.getUTCMonth(),
          start.getUTCDate() + index,
        ),
      );
      const key = this.dateKey(
        day.getUTCFullYear(),
        day.getUTCMonth() + 1,
        day.getUTCDate(),
      );
      cells.push({
        key,
        day: day.getUTCDate(),
        currentMonth: day.getUTCMonth() === month,
        appointments: byDate.get(key) ?? [],
      });
    }

    return cells;
  }

  private businessDateKey(value: string): string {
    const parsed = new Date(value);
    const parts = new Intl.DateTimeFormat('en-US', {
      timeZone: 'America/Tijuana',
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
    }).formatToParts(parsed);

    return [
      this.datePart(parts, 'year'),
      this.datePart(parts, 'month'),
      this.datePart(parts, 'day'),
    ].join('-');
  }

  private currentBusinessMonth(): string {
    const now = new Date();
    const parts = new Intl.DateTimeFormat('en-US', {
      timeZone: 'America/Tijuana',
      year: 'numeric',
      month: '2-digit',
    }).formatToParts(now);
    return [
      this.datePart(parts, 'year'),
      this.datePart(parts, 'month'),
    ].join('-');
  }

  private datePart(
    parts: Intl.DateTimeFormatPart[],
    type: 'year' | 'month' | 'day',
  ): string {
    return parts.find((part) => part.type === type)?.value ?? '';
  }

  private firstDayOfBusinessMonth(): Date {
    const [year, month] = this.currentBusinessMonth()
      .split('-')
      .map(Number);
    return new Date(Date.UTC(year, month - 1, 1));
  }

  private dateKey(
    year: number,
    month: number,
    day: number,
  ): string {
    return [
      String(year).padStart(4, '0'),
      String(month).padStart(2, '0'),
      String(day).padStart(2, '0'),
    ].join('-');
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

  private clearFeedback(): void {
    this.feedbackMessage = '';
    this.feedbackKind = 'INFO';
  }
}