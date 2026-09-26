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
}

export interface AttendanceTypeDistribution {
  attendance_type: string;
  visits: number;
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
