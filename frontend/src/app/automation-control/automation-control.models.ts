export interface Job { key:string; label:string; domain:string; worker_key:string; schedule_reference:string; priority_policy:string; run_history_coverage:string; worker_health:string; manual_run_supported:boolean; }
export interface Run { run_id:number; business_date:string|null; started_at_utc:string|null; finished_at_utc:string|null; status_raw:string; is_canonical:boolean|null; is_current:boolean|null; version_type?:string; error_available:boolean; }
export interface RunsResponse { rows:Run[]; coverage:string; has_more:boolean; limit:number; offset:number; }
export interface Summary { worker_count:number; job_count:number; dataset_count:number; worker_health:string; manual_actions_enabled:boolean; }
export interface Dataset { key:string; label:string; data_freshness:string; latest_complete_business_date:string|null; sources:unknown[]; }
