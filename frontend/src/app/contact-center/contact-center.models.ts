export type ContactCenterSource =
  | 'CRM'
  | 'MESSAGE'
  | 'REACTIVATION'
  | 'CAMPAIGN'
  | 'MANUAL';

export type ContactCenterCaseStatus =
  | 'NEW'
  | 'IN_PROGRESS'
  | 'FOLLOW_UP'
  | 'APPOINTMENT'
  | 'CLOSED';

export type ContactCenterInteractionOutcome =
  | 'NO_ANSWER'
  | 'CALL_BACK'
  | 'INTERESTED'
  | 'APPOINTMENT'
  | 'NOT_INTERESTED'
  | 'WRONG_NUMBER'
  | 'DO_NOT_CONTACT'
  | 'NOTE';

export type ContactCenterAppointmentOutcome =
  | 'ATTENDED_PURCHASE_REPORTED'
  | 'ATTENDED_NO_PURCHASE'
  | 'NO_SHOW'
  | 'CANCELLED'
  | 'RESCHEDULED';

export interface ContactCenterBranch {
  id: number;
  name: string;
}

export interface ContactCenterUserRef {
  id: number;
  username: string;
  role: string;
}

export interface ContactCenterAccess {
  allowed: boolean;
  user: ContactCenterUserRef;
  is_supervisor: boolean;
}

export interface ContactCenterCase {
  id: number;
  contact_id: number;
  source_type: ContactCenterSource;
  source_ref: string | null;
  sucursal: ContactCenterBranch | null;
  assigned_user: ContactCenterUserRef | null;
  status: ContactCenterCaseStatus;
  next_action_at: string | null;
  opened_at: string;
  closed_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface ContactCenterContact {
  id: number;
  display_name: string | null;
  primary_phone_raw: string;
  phone_mx10: string | null;
  email: string | null;
  preferred_sucursal: ContactCenterBranch | null;
  is_active: boolean;
  merged_into_contact_id: number | null;
  created_at: string;
  updated_at: string;
  case?: ContactCenterCase;
}

export interface ContactCenterInteraction {
  id: number;
  case_id: number;
  contact_id: number;
  interaction_type: 'CALL' | 'MESSAGE' | 'NOTE' | 'SYSTEM';
  outcome: ContactCenterInteractionOutcome;
  comment: string | null;
  next_action_at: string | null;
  created_by_user: ContactCenterUserRef | null;
  created_at: string;
}

export interface ContactCenterAppointment {
  id: number;
  case_id: number;
  contact_id: number;
  sucursal: ContactCenterBranch | null;
  scheduled_at: string;
  timezone: string;
  status: 'SCHEDULED' | 'CANCELLED' | 'RESCHEDULED' | 'CLOSED';
  outcome: ContactCenterAppointmentOutcome | null;
  notes: string | null;
  closure_pending: boolean;
  closed_at: string | null;
  rescheduled_to_appointment_id: number | null;
  purchase_reported: boolean;
  purchase_reported_at: string | null;
  purchase_verification_status:
    | 'NOT_REPORTED'
    | 'REPORTED_PENDING'
    | 'VERIFIED'
    | 'REVIEW'
    | 'NOT_FOUND_YET';
  venta_total_snapshot_id: number | null;
  venta_total_snapshot_row_id: number | null;
  verified_purchase_at: string | null;
  verified_amount: number | null;
  verified_tariff: string | null;
  created_at: string;
  updated_at: string;
  contact?: ContactCenterContact;
  case?: ContactCenterCase;
}

export interface ContactCenterContactDetail extends ContactCenterContact {
  cases: ContactCenterCase[];
  interactions: ContactCenterInteraction[];
  appointments: ContactCenterAppointment[];
  links: Array<{
    id: number;
    source_type: string;
    source_key: string;
    source_row_id: number | null;
    source_metadata: Record<string, unknown> | null;
  }>;
}

export interface ContactCenterLookups {
  branches: ContactCenterBranch[];
  agents: ContactCenterUserRef[];
}

export interface ContactCenterCrmCandidate {
  contact_row_id: number;
  source_key: string;
  sucursal_id: number;
  sucursal: string | null;
  contact_id: string;
  name: string | null;
  phone: string | null;
  first_message_at_local: string | null;
  channel_name: string | null;
  channel_platform: string | null;
  already_in_contact_center: boolean;
}

export interface ContactCenterCrmCandidatesResponse {
  period_key: string;
  sync_run_id: number | null;
  rows: ContactCenterCrmCandidate[];
}

export interface ContactCenterReportSummary {
  active_cases: number;
  new: number;
  in_progress: number;
  follow_up: number;
  appointment_cases: number;
  appointments: number;
  closure_pending: number;
  purchase_reported: number;
  purchase_verified: number;
}

export interface ContactCenterReport {
  summary: ContactCenterReportSummary;
  appointments: ContactCenterAppointment[];
}

export interface ContactCenterCalendarCell {
  key: string;
  day: number;
  currentMonth: boolean;
  appointments: ContactCenterAppointment[];
}
