export interface SportsAnalysisContext {
  allowed: boolean;
  user: {
    id: number;
    username: string;
    role: string;
  };
  scope: SportsAnalysisScope;
}

export interface SportsAnalysisScope {
  role: string;
  is_global: boolean;
  allowed_branch_ids: number[];
  fixed_branch_id: number | null;
}

export interface AttendanceBranch {
  id: number;
  name: string;
  track_label: string;
  display_order: number;
  region_key: string | null;
  region_name: string | null;
}

export interface AttendanceRegion {
  key: string;
  name: string;
  branch_ids: number[];
}

export interface AttendanceCatalogs {
  scope: SportsAnalysisScope;
  branches: AttendanceBranch[];
  regions: AttendanceRegion[];
  attendance_types: string[];
  default_attendance_type: string;
  latest_business_date: string | null;
}

export interface AttendanceDashboardFilters {
  date_from: string | null;
  date_to: string | null;
  branch_id: number | null;
  region_key: string | null;
  attendance_type: string;
}

export interface AttendanceDashboardRequest {
  dateFrom: string;
  dateTo: string;
  branchId: number | null;
  regionKey: string | null;
  attendanceType: string;
}

export interface AttendanceSummary {
  visits: number;
  unique_members: number;
  peak_occupancy: number;
  peak_business_date: string | null;
  peak_minute: number | null;
  average_duration_seconds: number | null;
  median_duration_seconds: number | null;
}

export interface AttendanceInterval {
  minute: number;
  occupancy: number;
  entries: number;
  exits: number;
}

export interface AttendanceHour {
  hour: number;
  entries: number;
}

export interface AttendanceAgeBucket {
  label: string;
  visits: number;
  unique_members: number;
}

export interface AttendanceTypeDistribution {
  attendance_type: string;
  visits: number;
  unique_members: number;
}

export interface AttendanceBranchRanking {
  branch_id: number;
  branch_name: string;
  region_key: string | null;
  visits: number;
  unique_members: number;
  peak_occupancy: number;
}

export interface AttendanceDataQuality {
  closed: number;
  open: number;
  cross_day: number;
  invalid_time: number;
  unresolved_branch: number;
  non_operational_excluded: number;
}

export interface AttendanceDashboard {
  scope: Omit<SportsAnalysisScope, 'fixed_branch_id'>;
  filters: AttendanceDashboardFilters;
  summary: AttendanceSummary;
  occupancy_profile: AttendanceInterval[];
  entries_by_hour: AttendanceHour[];
  age_distribution: AttendanceAgeBucket[];
  attendance_type_distribution: AttendanceTypeDistribution[];
  branch_ranking: AttendanceBranchRanking[];
  data_quality: AttendanceDataQuality;
}


export type AttendanceDashboardView =
  | 'summary'
  | 'base-health'
  | 'operations';

export interface AttendanceBaseHealthRequest {
  dateFrom: string;
  dateTo: string;
  branchId: number | null;
  regionKey: string | null;
}

export interface AttendanceBaseHealthFilters {
  date_from: string;
  date_to: string;
  branch_id: number | null;
  region_key: string | null;
  attendance_type: 'SOCIO';
}

export interface AttendanceBaseHealthSummary {
  eligible_members: number;
  members_with_visit: number;
  members_without_visit: number;
  utilization_pct: number;
  without_visit_pct: number;
  frequency_avg_per_week: number;
  frequency_median_per_week: number;
  members_14_plus_days_without_visit: number;
  follow_up_members: number;
}

export interface AttendanceBaseHealthDistributionBucket {
  key: string;
  label: string;
  count: number;
  pct: number;
}

export interface AttendanceBaseHealthActivation {
  new_members: number;
  distribution: AttendanceBaseHealthDistributionBucket[];
}

export interface AttendanceBaseHealthSource {
  available: boolean;
  snapshot_count: number;
  first_snapshot_date: string | null;
  last_snapshot_date: string | null;
  identity_coverage_pct: number;
  visits_checked: number;
  visits_resolved: number;
  effective_branch_ids: number[];
}

export interface AttendanceBaseHealth {
  scope: Omit<SportsAnalysisScope, 'fixed_branch_id'>;
  filters: AttendanceBaseHealthFilters;
  summary: AttendanceBaseHealthSummary;
  frequency_distribution: AttendanceBaseHealthDistributionBucket[];
  recency_distribution: AttendanceBaseHealthDistributionBucket[];
  activation: AttendanceBaseHealthActivation;
  source: AttendanceBaseHealthSource;
}

export type AttendanceBaseHealthMemberStatus =
  | 'WITH_VISIT'
  | 'WITHOUT_VISIT'
  | 'FOLLOW_UP'
  | 'RECENCY_14_PLUS'
  | 'RECENCY_0_7'
  | 'RECENCY_8_14'
  | 'RECENCY_15_21'
  | 'RECENCY_22_PLUS'
  | 'RECENCY_NO_RECORDED'
  | 'FREQUENCY_ZERO'
  | 'FREQUENCY_LT_1'
  | 'FREQUENCY_1_1_99'
  | 'FREQUENCY_2_2_99'
  | 'FREQUENCY_GTE_3';

export interface AttendanceBaseHealthMemberRow {
  id_socio: string;
  name: string | null;
  branch_id: number;
  branch_name: string;
  pin: string;
  member_since: string | null;
  has_visit: boolean;
  visit_count: number;
  last_visit_date: string | null;
  days_since_last_visit: number | null;
  frequency_per_week: number;
}

export interface AttendanceBaseHealthMembersRequest
  extends AttendanceBaseHealthRequest {
  status: AttendanceBaseHealthMemberStatus;
  page?: number;
  pageSize?: number;
}

export interface AttendanceBaseHealthMembersResponse {
  status: AttendanceBaseHealthMemberStatus;
  title: string;
  count: number;
  page: number;
  page_size: number;
  total_pages: number;
  rows: AttendanceBaseHealthMemberRow[];
}


export type AttendanceDetailSortDirection = 'asc' | 'desc';

export interface AttendanceDetailColumn {
  key: string;
  label: string;
  sortable?: boolean;
}

export type AttendanceDetailRow = Record<
  string,
  string | number | boolean | null
>;

export interface AttendanceDetailResponse {
  metric: string;
  title: string;
  count: number;
  page: number;
  page_size: number;
  total_pages: number;
  sort_by: string;
  sort_dir: AttendanceDetailSortDirection;
  columns: AttendanceDetailColumn[];
  rows: AttendanceDetailRow[];
}

export interface AttendanceDetailRequest
  extends AttendanceDashboardRequest {
  metric: string;
  page?: number;
  pageSize?: number;
  sortBy?: string;
  sortDir?: AttendanceDetailSortDirection;
  minute?: number;
  hour?: number;
  ageBucket?: string;
}
