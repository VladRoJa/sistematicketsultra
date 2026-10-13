export interface Job { key:string; label:string; domain:string; worker_key:string; schedule_reference:string; priority_policy:string; run_history_coverage:string; worker_health:string; manual_run_supported:boolean; }
export interface Run { run_id:number; business_date:string|null; started_at_utc:string|null; finished_at_utc:string|null; status_raw:string; is_canonical:boolean|null; is_current:boolean|null; version_type?:string; evidence_type?:string; observed_at_utc?:string|null; error_available:boolean; }
export interface RunsResponse { rows:Run[]; coverage:string; has_more:boolean; limit:number; offset:number; }
export interface Summary { worker_count:number; job_count:number; dataset_count:number; worker_health:string; manual_actions_enabled:boolean; }
export interface Dataset { key:string; label:string; data_freshness:string; latest_complete_business_date:string|null; sources:unknown[]; }

export interface TimelineObservation extends Run { observed_hour:string; observed_time:string; }
export interface TimelineJob {
  job_key:string;label:string;schedule_kind:string;reference_slots:string[];
  schedule_verified:boolean;coverage:string;observed:Record<string,TimelineObservation[]>;
}
export interface TimelineWorker { worker_key:string;jobs:TimelineJob[]; }
export interface TimelineResponse { date:string;timezone:string;schedule_verified:boolean;workers:TimelineWorker[]; }

export interface AutomationDiagnostic {
  job_key:string; run_id:number|null; business_date:string|null;
  status?:string; started_at_utc?:string|null; finished_at_utc?:string|null;
  diagnostic_state:string; error_code?:string|null; sanitized_message:string;
  failed_stage?:string|null; correlation_id?:string|null;
  log_lines:string[]; truncated:boolean; source?:string; failure_recency?:string;
  log_state?:string; counts?:{
    branches_requested:number;branches_completed:number;branches_failed:number;
    aliases_unresolved:number;
  };
  branch_failures?:{branch_code:string;error_type:string}[];
  failure_details_coverage?:string;
  failure_details_truncated?:boolean;
}
