export type RoutineControlScopeType = 'BRANCH' | 'REGIONAL' | 'GLOBAL';
export type RoutineControlVisibleStatus = 'SIN_RUTINA' | 'CON_RUTINA' | 'NO_DESEA_RUTINA' | 'INCIDENT';
export type RoutineControlAssignmentType = 'PREEXISTENTE' | 'MISMO_DIA' | 'POSTERIOR';

export interface RoutineControlScope {
  scope_type: RoutineControlScopeType;
  allowed_branch_ids: number[];
  fixed_branch_id: number | null;
}

export interface RoutineControlBranchCatalog {
  id: number;
  name: string;
  region_key: string | null;
  region_name: string | null;
}

export interface RoutineControlRegionCatalog {
  key: string;
  name: string;
  branch_ids: number[];
}

export interface RoutineControlCatalogs {
  scope: RoutineControlScope;
  branches: RoutineControlBranchCatalog[];
  regions: RoutineControlRegionCatalog[];
  statuses: RoutineControlVisibleStatus[];
  assignment_types: RoutineControlAssignmentType[];
}

export interface RoutineControlFilters {
  branch_id?: number | null;
  region_key?: string | null;
  sale_date_from?: string | null;
  sale_date_to?: string | null;
  classification_status?: 'CLASSIFIED' | 'INCIDENT' | null;
  current_status?: Exclude<RoutineControlVisibleStatus, 'INCIDENT'> | null;
  assignment_type?: RoutineControlAssignmentType | null;
  instructor?: string | null;
  search?: string | null;
  page?: number;
  page_size?: number;
  sort?: string;
  direction?: 'asc' | 'desc';
}

export interface RoutineControlSummaryBranch {
  branch_id: number | null;
  branch_name: string;
  total_members: number;
  sin_rutina: number;
  con_rutina: number;
  no_desea_rutina: number;
  incidents: number;
}

export interface RoutineControlFreshness {
  last_successful_pipeline_at_utc: string | null;
  last_gasca_success_at_utc: string | null;
  last_trainingym_success_at_utc: string | null;
}

export interface RoutineControlSummary {
  filters_applied: Record<string, string | number | null>;
  total_members: number;
  classified_members: number;
  incident_members: number;
  status_counts: Record<RoutineControlVisibleStatus, number>;
  assignment_type_counts: Record<RoutineControlAssignmentType | 'SIN_EVIDENCIA', number>;
  branches: RoutineControlSummaryBranch[];
  freshness: RoutineControlFreshness;
}

export interface RoutineControlMember {
  id: number;
  external_member_id: string;
  external_sale_id: string | null;
  member_name: string | null;
  email: string | null;
  branch_id: number | null;
  branch_name: string | null;
  source_branch_name: string | null;
  sale_date: string;
  classification_status: 'CLASSIFIED' | 'INCIDENT';
  current_status: Exclude<RoutineControlVisibleStatus, 'INCIDENT'> | null;
  first_routine_at: string | null;
  latest_routine_at: string | null;
  current_instructor_name: string | null;
  routine_assignment_type: RoutineControlAssignmentType | null;
  status_version: number;
  active_incident_count: number;
  active_evidence_count: number;
}

export interface RoutineControlMembersResponse {
  items: RoutineControlMember[];
  page: number;
  page_size: number;
  total: number;
  total_pages: number;
}

export interface RoutineControlEvidence {
  id: number;
  provider_key: string;
  provider_member_id: string;
  external_member_id: string | null;
  routine_activity_date: string;
  instructor_name: string;
  routine_count: number;
  weighing_count: number;
  provider_center_name: string;
  match_method: 'EXTERNAL_ID' | 'EMAIL';
  linked_at_utc: string;
  is_valid: boolean;
}

export interface RoutineControlIncident {
  id: number;
  incident_type: string;
  is_blocking: boolean;
  is_active: boolean;
  detected_at_utc: string;
  resolved_at_utc: string | null;
  resolution_note: string | null;
}

export interface RoutineControlDecision {
  id: number;
  decision_type: string;
  is_active: boolean;
  decided_at_utc: string;
  effective_from_utc: string;
  effective_to_utc: string | null;
  revoked_at_utc: string | null;
  decision_reason: string | null;
}

export interface RoutineControlMemberDetail {
  member: RoutineControlMember;
  evidences: RoutineControlEvidence[];
  incidents: RoutineControlIncident[];
  decisions: RoutineControlDecision[];
}

export interface RoutineControlProviderRun {
  id: number;
  provider_key: string;
  dataset_key: string;
  status: string;
  started_at_utc: string | null;
  finished_at_utc: string | null;
  records_read: number;
  records_accepted: number;
  records_rejected: number;
  error_message: string | null;
}

export interface RoutineControlRun extends Omit<RoutineControlProviderRun, 'provider_key' | 'dataset_key'> {
  mode: string;
  created_at_utc: string;
  provider_runs: RoutineControlProviderRun[];
}

export interface RoutineControlRunsResponse {
  items: RoutineControlRun[];
  page: number;
  page_size: number;
  total: number;
  total_pages: number;
}

export interface RoutineControlRunFilters {
  status?: string | null;
  date_from?: string | null;
  date_to?: string | null;
  page?: number;
  page_size?: number;
}
