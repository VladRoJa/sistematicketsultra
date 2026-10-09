export type SystemDailyCheckAnswerValue = 'YES' | 'NO' | 'NA';
export type SystemDailyCheckGeneralStatus =
  | 'NORMAL'
  | 'MINOR_FAILURE'
  | 'OPERATIONAL_IMPACT';
export type SystemDailyCheckMatrixState =
  | 'GREEN'
  | 'YELLOW'
  | 'RED'
  | 'PENDING'
  | 'NA'
  | 'UNKNOWN';
export type SystemDailyCheckGranularity = 'DAY' | 'WEEK' | 'MONTH';

export interface SystemDailyCheckQuestion {
  question_key: string;
  label: string;
  category_key: string | null;
  requires_affected_scope: boolean;
}

export interface SystemDailyCheckBranch {
  sucursal_id: number;
  sucursal: string;
  serie: string;
  operational_status: string;
  is_demo: boolean;
  enabled_from?: string;
  disabled_from?: string | null;
}

export interface SystemDailyCheckUniverse {
  as_of_date: string;
  potential_branches: SystemDailyCheckBranch[];
  expected_branches: SystemDailyCheckBranch[];
  potential_count: number;
  expected_count: number;
}

export interface SystemDailyCheckBiContext {
  allowed: boolean;
  user: {
    id: number;
    username: string;
    role: string;
  };
  business_date: string;
  questions: SystemDailyCheckQuestion[];
  universe: SystemDailyCheckUniverse;
}

export interface SystemDailyCheckSummary {
  filters: {
    date_from: string;
    date_to: string;
    branch_id: number | null;
  };
  universe: {
    expected_checklists: number;
    expected_branches: number;
    out_of_rollout_submissions: number;
  };
  summary: {
    completed: number;
    pending: number;
    compliance_pct: number | null;
    normal: number;
    minor_failure: number;
    operational_impact: number;
  };
  failures: {
    checks_with_failure: number;
    no_answers: number;
    issues_total: number;
    reported: number;
    unreported: number;
    reported_pct: number | null;
  };
  postponements: {
    completed_without_postpone: number;
    completed_after_1: number;
    completed_after_2: number;
    reached_mandatory: number;
  };
}

export interface SystemDailyCheckMatrixCell {
  state: SystemDailyCheckMatrixState;
  label: string;
}

export interface SystemDailyCheckMatrixGroup {
  key: string;
  label: string;
  question_keys: string[];
}

export interface SystemDailyCheckMatrixRow {
  sucursal_id: number;
  sucursal: string;
  check_id: number | null;
  general_status: SystemDailyCheckGeneralStatus | null;
  submitted_at: string | null;
  postpone_count: number;
  cells: Record<string, SystemDailyCheckMatrixCell>;
}

export interface SystemDailyCheckMatrix {
  business_date: string;
  branch_id: number | null;
  groups: SystemDailyCheckMatrixGroup[];
  rows: SystemDailyCheckMatrixRow[];
}

export interface SystemDailyCheckTrendRow {
  period_start: string;
  period_end: string;
  expected: number;
  completed: number;
  pending: number;
  compliance_pct: number | null;
  normal: number;
  minor_failure: number;
  operational_impact: number;
  no_answers: number;
  issues_total: number;
  reported: number;
  unreported: number;
  reported_pct: number | null;
  completed_without_postpone: number;
  completed_after_1: number;
  completed_after_2: number;
  reached_mandatory: number;
}

export interface SystemDailyCheckQuestionRanking {
  question_key: string;
  question_label: string;
  no_answers: number;
  issues_total: number;
  reported: number;
  reported_pct: number | null;
  affected_branches: number;
  distinct_days: number;
}

export interface SystemDailyCheckBranchRanking {
  sucursal_id: number;
  sucursal: string | null;
  expected: number;
  completed: number;
  pending: number;
  checks_with_failure: number;
  no_answers: number;
  issues_total: number;
  reported: number;
  reported_pct: number | null;
}

export interface SystemDailyCheckRecurrence {
  sucursal_id: number;
  sucursal: string | null;
  question_key: string;
  question_label: string;
  distinct_days: number;
  first_business_date: string;
  last_business_date: string;
}

export interface SystemDailyCheckTrends {
  filters: {
    date_from: string;
    date_to: string;
    branch_id: number | null;
    granularity: SystemDailyCheckGranularity;
    week_convention: string | null;
  };
  trend: SystemDailyCheckTrendRow[];
  question_ranking: SystemDailyCheckQuestionRanking[];
  branch_ranking: SystemDailyCheckBranchRanking[];
  recurrence: SystemDailyCheckRecurrence[];
}

export interface SystemDailyCheckHistoryItem {
  id: number;
  sucursal_id: number;
  sucursal: string;
  performed_by_user_id: number;
  performed_by_username: string | null;
  business_date: string;
  general_status: SystemDailyCheckGeneralStatus;
  submitted_at: string | null;
  postpone_count: number;
  reached_mandatory: boolean;
}

export interface SystemDailyCheckHistory {
  filters: {
    date_from: string;
    date_to: string;
    branch_id: number | null;
    general_status: SystemDailyCheckGeneralStatus | null;
    question_key: string | null;
    answer: SystemDailyCheckAnswerValue | null;
  };
  page: number;
  page_size: number;
  total: number;
  items: SystemDailyCheckHistoryItem[];
}

export interface SystemDailyCheckPendingItem {
  sucursal_id: number;
  sucursal: string | null;
  business_date: string;
  postpone_count: number;
  mandatory: boolean;
  next_prompt_at: string | null;
  mandatory_from_at: string | null;
}

export interface SystemDailyCheckPending {
  filters: {
    date_from: string;
    date_to: string;
    branch_id: number | null;
  };
  page: number;
  page_size: number;
  total: number;
  items: SystemDailyCheckPendingItem[];
}

export interface SystemDailyCheckAttachment {
  id: number;
  original_filename: string;
  mime_type: string;
  file_size_bytes: number;
  sha256: string;
  url: string;
}

export interface SystemDailyCheckIssue {
  id: number;
  affected_scope: 'ONE' | 'MULTIPLE' | null;
  reported_to_support: boolean;
  description: string;
  attachments: SystemDailyCheckAttachment[];
}

export interface SystemDailyCheckDetailAnswer {
  id: number;
  question_key: string;
  question_label: string;
  category_key: string | null;
  answer: SystemDailyCheckAnswerValue;
  issue: SystemDailyCheckIssue | null;
}

export interface SystemDailyCheckDetail {
  id: number;
  sucursal_id: number;
  sucursal: string;
  performed_by_user_id: number;
  performed_by_username: string | null;
  business_date: string;
  general_status: SystemDailyCheckGeneralStatus;
  created_at: string | null;
  submitted_at: string | null;
  prompt: {
    postpone_count: number;
    last_postponed_at: string | null;
    mandatory_from_at: string | null;
    reached_mandatory: boolean;
  };
  answer_count: number;
  answers: SystemDailyCheckDetailAnswer[];
}

export interface SystemDailyCheckFilters {
  dateFrom: string;
  dateTo: string;
  branchId: number | null;
}


export interface SystemDailyCheckIssueDrilldownItem {
  issue_id: number;
  check_id: number;
  sucursal_id: number;
  sucursal: string;
  business_date: string;
  question_key: string;
  question_label: string;
  reported_to_support: boolean;
  affected_scope: 'ONE' | 'MULTIPLE' | null;
  description: string;
  attachment_count: number;
}

export interface SystemDailyCheckIssuesDrilldown {
  filters: {
    date_from: string;
    date_to: string;
    branch_id: number | null;
    question_key: string | null;
    reported_to_support: boolean | null;
  };
  page: number;
  page_size: number;
  total: number;
  items: SystemDailyCheckIssueDrilldownItem[];
}
