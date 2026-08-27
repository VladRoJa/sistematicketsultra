export type ReactivationCandidateStatus =
  | 'EXCLUDED_ACTIVE'
  | 'REVIEW_ACTIVE_MATCH'
  | 'EXCLUDED_POST_EXPIRATION_CONTACT'
  | 'CONTACT_HISTORY_UNKNOWN';

export type ReactivationCandidateReason =
  | 'ACTIVE_CONFIRMED'
  | 'ACTIVE_REVIEW'
  | 'AMBIGUOUS'
  | 'IDENTIFIER_CONFLICT'
  | 'POST_EXPIRATION_OUTBOUND'
  | 'NO_MX10'
  | 'DUPLICATE_VENCIDO_PHONE'
  | 'NO_MATCH_CURRENT_IVENTAS_RUN'
  | 'AMBIGUOUS_IVENTAS_IDENTITY'
  | 'NO_OUTBOUND_EVIDENCE'
  | 'ONLY_PRE_EXPIRATION_OUTBOUND';

export interface ReactivationVencidosSnapshot {
  id: number;
  date_from: string;
  date_to: string;
  snapshot_kind: string | null;
  row_count: number;
}

export interface ReactivationIventasPeriod {
  period_key: string;
  sync_run_id: number;
  date_from: string;
  date_to: string;
  contacts_unique: number;
}

export interface ReactivationSourcesResponse {
  vencidos_snapshots: ReactivationVencidosSnapshot[];
  iventas_periods: ReactivationIventasPeriod[];
}

export interface ReactivationCandidateSources {
  vencidos_snapshot_id: number;
  activos_snapshot_id: number;
  iventas_sync_run_id: number;
  iventas_period_key: string;
}

export interface ReactivationSummary {
  total_rows: number;
  status_counts: Record<ReactivationCandidateStatus, number>;
  reason_counts: Record<ReactivationCandidateReason, number>;
}

export interface ReactivationCandidateRow {
  vencido_row_id: number;
  pin: string;
  nombre: string | null;
  sucursal: string;
  telefono: string | null;
  correo: string | null;
  fecha_vencimiento: string;
  fecha_ultimo_pago: string | null;
  tarifa: string | null;
  adeudo: string | null;
  status: ReactivationCandidateStatus;
  reason: ReactivationCandidateReason;
  active_status: string;
  active_id_socio: string | null;
  iventas_contact_id: string | null;
  latest_outbound_at_utc: string | null;
}

export interface ReactivationCandidatesResponse {
  sources: ReactivationCandidateSources;
  summary: ReactivationSummary;
  rows: ReactivationCandidateRow[];
}
