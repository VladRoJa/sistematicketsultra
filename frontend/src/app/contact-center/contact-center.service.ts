import { HttpClient, HttpParams } from '@angular/common/http';
import { Injectable } from '@angular/core';
import { Observable } from 'rxjs';

import { environment } from 'src/environments/environment';
import {
  ContactCenterAccess,
  ContactCenterAppointment,
  ContactCenterAppointmentOutcome,
  ContactCenterContact,
  ContactCenterContactDetail,
  ContactCenterCrmCandidatesResponse,
  ContactCenterInteraction,
  ContactCenterInteractionOutcome,
  ContactCenterLookups,
  ContactCenterReport,
  ContactCenterSource,
} from './contact-center.models';


@Injectable({ providedIn: 'root' })
export class ContactCenterService {
  private readonly apiUrl = `${environment.apiUrl}/contact-center`;

  constructor(private readonly http: HttpClient) {}

  getAccess(): Observable<ContactCenterAccess> {
    return this.http.get<ContactCenterAccess>(`${this.apiUrl}/access`);
  }

  getLookups(): Observable<ContactCenterLookups> {
    return this.http.get<ContactCenterLookups>(`${this.apiUrl}/lookups`);
  }

  getContacts(filters?: {
    status?: string;
    source_type?: string;
    q?: string;
  }): Observable<{ rows: ContactCenterContact[]; count: number }> {
    let params = new HttpParams();
    if (filters?.status) {
      params = params.set('status', filters.status);
    }
    if (filters?.source_type) {
      params = params.set('source_type', filters.source_type);
    }
    if (filters?.q) {
      params = params.set('q', filters.q);
    }

    return this.http.get<{ rows: ContactCenterContact[]; count: number }>(
      `${this.apiUrl}/contacts`,
      { params },
    );
  }

  getContact(contactId: number): Observable<ContactCenterContactDetail> {
    return this.http.get<ContactCenterContactDetail>(
      `${this.apiUrl}/contacts/${contactId}`,
    );
  }

  createContact(payload: {
    name?: string | null;
    phone: string;
    email?: string | null;
    sucursal_id?: number | null;
    source_type: ContactCenterSource;
    source_ref?: string | null;
    comment?: string | null;
    assigned_user_id?: number | null;
  }): Observable<{
    contact: ContactCenterContact;
    case: ContactCenterContact['case'];
  }> {
    return this.http.post<any>(`${this.apiUrl}/contacts`, payload);
  }

  findDuplicates(filters: {
    phone?: string | null;
    email?: string | null;
    exclude_contact_id?: number | null;
  }): Observable<{ rows: ContactCenterContact[]; count: number }> {
    let params = new HttpParams();

    if (filters.phone) {
      params = params.set('phone', filters.phone);
    }
    if (filters.email) {
      params = params.set('email', filters.email);
    }
    if (filters.exclude_contact_id) {
      params = params.set(
        'exclude_contact_id',
        String(filters.exclude_contact_id),
      );
    }

    return this.http.get<{ rows: ContactCenterContact[]; count: number }>(
      `${this.apiUrl}/contacts/duplicates`,
      { params },
    );
  }

  mergeContacts(payload: {
    survivor_contact_id: number;
    merged_contact_id: number;
    field_resolution: Record<string, unknown>;
  }): Observable<{ contact: ContactCenterContact; merged_contact_id: number }> {
    return this.http.post<any>(
      `${this.apiUrl}/contacts/merge`,
      payload,
    );
  }

  assignCase(
    caseId: number,
    assignedUserId: number,
  ): Observable<{ case: any }> {
    return this.http.post<any>(
      `${this.apiUrl}/cases/${caseId}/assign`,
      { assigned_user_id: assignedUserId },
    );
  }

  addInteraction(
    caseId: number,
    payload: {
      interaction_type: 'CALL' | 'MESSAGE' | 'NOTE';
      outcome: ContactCenterInteractionOutcome;
      comment?: string | null;
      next_action_at?: string | null;
    },
  ): Observable<{ interaction: ContactCenterInteraction }> {
    return this.http.post<{ interaction: ContactCenterInteraction }>(
      `${this.apiUrl}/cases/${caseId}/interactions`,
      payload,
    );
  }

  createAppointment(
    caseId: number,
    payload: {
      sucursal_id: number;
      scheduled_at: string;
      notes?: string | null;
    },
  ): Observable<{
    appointment: ContactCenterAppointment;
    notification: {
      queued: boolean;
      recipients: string[];
      status: string;
    };
  }> {
    return this.http.post<any>(
      `${this.apiUrl}/cases/${caseId}/appointments`,
      payload,
    );
  }

  getAppointments(filters?: {
    date_from?: string;
    date_to?: string;
  }): Observable<{ rows: ContactCenterAppointment[]; count: number }> {
    let params = new HttpParams();
    if (filters?.date_from) {
      params = params.set('date_from', filters.date_from);
    }
    if (filters?.date_to) {
      params = params.set('date_to', filters.date_to);
    }

    return this.http.get<{ rows: ContactCenterAppointment[]; count: number }>(
      `${this.apiUrl}/appointments`,
      { params },
    );
  }

  closeAppointment(
    appointmentId: number,
    payload: {
      outcome: Exclude<ContactCenterAppointmentOutcome, 'RESCHEDULED'>;
      notes?: string | null;
    },
  ): Observable<{ appointment: ContactCenterAppointment }> {
    return this.http.post<{ appointment: ContactCenterAppointment }>(
      `${this.apiUrl}/appointments/${appointmentId}/close`,
      payload,
    );
  }

  rescheduleAppointment(
    appointmentId: number,
    payload: {
      sucursal_id?: number | null;
      scheduled_at: string;
      notes?: string | null;
    },
  ): Observable<{
    appointment: ContactCenterAppointment;
    notification: {
      queued: boolean;
      recipients: string[];
      status: string;
    };
  }> {
    return this.http.post<any>(
      `${this.apiUrl}/appointments/${appointmentId}/reschedule`,
      payload,
    );
  }

  verifyPurchase(
    appointmentId: number,
  ): Observable<{ appointment: ContactCenterAppointment }> {
    return this.http.post<{ appointment: ContactCenterAppointment }>(
      `${this.apiUrl}/appointments/${appointmentId}/verify-purchase`,
      {},
    );
  }

  getCrmCandidates(
    month: string,
    phone?: string,
  ): Observable<ContactCenterCrmCandidatesResponse> {
    let params = new HttpParams();

    if (phone?.trim()) {
      params = params.set('phone', phone.trim());
    } else {
      params = params.set('month', month);
    }

    return this.http.get<ContactCenterCrmCandidatesResponse>(
      `${this.apiUrl}/crm-candidates`,
      { params },
    );
  }

  importCrmCandidate(
    contactRowId: number,
    targetContactId?: number | null,
    displayName?: string | null,
  ): Observable<{
    contact: ContactCenterContact;
    case: any;
  }> {
    const payload: {
      contact_id?: number;
      display_name?: string;
    } = {};

    if (targetContactId) {
      payload.contact_id = targetContactId;
    }
    if (displayName?.trim()) {
      payload.display_name = displayName.trim();
    }

    return this.http.post<any>(
      `${this.apiUrl}/crm-candidates/${contactRowId}/import`,
      payload,
    );
  }

  getReport(filters?: {
    date_from?: string;
    date_to?: string;
  }): Observable<ContactCenterReport> {
    let params = new HttpParams();
    if (filters?.date_from) {
      params = params.set('date_from', filters.date_from);
    }
    if (filters?.date_to) {
      params = params.set('date_to', filters.date_to);
    }

    return this.http.get<ContactCenterReport>(
      `${this.apiUrl}/report`,
      { params },
    );
  }
}