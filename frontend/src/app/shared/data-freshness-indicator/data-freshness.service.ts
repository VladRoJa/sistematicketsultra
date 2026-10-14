import { HttpClient, HttpParams } from '@angular/common/http';
import { Injectable } from '@angular/core';
import { Observable } from 'rxjs';
import { environment } from '../../../environments/environment';

export type FreshnessDatasetKey = 'marketing.sales_funnel' | 'track.daily';
export type FreshnessStatus = 'UP_TO_DATE'|'LAGGING'|'LATE'|'NOT_DUE'|'DISABLED'|'UNKNOWN';
export interface FreshnessSource {
  key: string;
  latest_complete_business_date: string|null;
  complete: boolean|null;
  reason_code: string;
}
export interface TrackCatalogCoverage {
  matches_current_catalog: boolean;
  expected_branch_count: number;
  actual_branch_count: number|null;
  mart_row_count: number|null;
  missing_branch_codes: string[];
  unexpected_branch_codes: string[];
  duplicate_branch_codes: string[];
  wrong_date_row_count: number|null;
  wrong_generation_mode_row_count: number|null;
  roster_basis: string;
  historical_roster_verified: false;
  selected_version_type: string|null;
  selected_version_id: number|null;
}
export interface TrackCoverageReport {
  latest_selected_version_date: string|null;
  latest_catalog_matched_date: string|null;
  selected_version_count: number;
  ambiguous_current_version_dates: string[];
  current_catalog_valid: boolean;
  coverage: TrackCatalogCoverage|null;
  roster_basis: string;
  historical_roster_verified: false;
}
export interface TrackBaseSla {
  expected_business_date:string;
  due_at:string;
  late_at:string;
  phase_if_unavailable:'NOT_DUE'|'LAGGING'|'LATE';
  timezone:string;
  policy_key:string;
  applies_every_day:boolean;
  status:'NOT_DUE'|'LAGGING'|'LATE'|'UNKNOWN';
  reason_code:string;
  base_version_id:number|null;
  base_version_status:string|null;
  base_current_catalog_coverage:TrackCatalogCoverage|null;
  historical_roster_verified:false;
  canonical_close_sla:string;
}
export interface MarketingSyncSla {
  business_date: string;
  status: FreshnessStatus;
  reason_code: string;
  slot_at: string|null;
  due_at: string|null;
  late_at: string|null;
  timezone: string;
  scope: 'SYNC_ONLY_NOT_FUNNEL_CONSOLIDATED';
  sources: Array<{key:string; status:FreshnessStatus; reason_code:string}>;
}
export interface FunnelOperationalSla {
  expected_business_date: string;
  due_at: string;
  late_at: string;
  phase_if_unavailable: 'NOT_DUE'|'LAGGING'|'LATE';
  timezone: string;
  policy_key: string;
  applies_every_day: boolean;
  status: 'NOT_DUE'|'LAGGING'|'LATE'|'UNKNOWN';
  reason_code: string;
  sources: Array<{key:string; present:boolean|null; reason_code:string}>;
  missing_sources: string[];
  operational_not_final: true;
  lineage_verified: false;
  historical_roster_verified: false;
  canonical_close_sla: string;
}
export interface DatasetFreshness {
  funnel_operational_sla?: FunnelOperationalSla;
  marketing_sync_sla?: MarketingSyncSla;
  track_base_sla?:TrackBaseSla;
  late_at?:string|null;
  latest_catalog_matched_business_date?: string|null;
  track_coverage?: TrackCoverageReport;
  module_key: FreshnessDatasetKey;
  dataset_key: FreshnessDatasetKey;
  status: FreshnessStatus;
  label: string;
  detail: string;
  reason_code: string;
  checked_at: string;
  timezone: string;
  expected_business_date: string|null;
  latest_complete_business_date: string|null;
  latest_observed_business_date: string|null;
  due_at: string|null;
  next_due_at: string|null;
  sources: FreshnessSource[];
}

@Injectable({providedIn:'root'})
export class DataFreshnessService {
  private readonly url = `${environment.apiUrl}/automation-control/freshness`;
  constructor(private readonly http: HttpClient) {}
  get(
    moduleKey: FreshnessDatasetKey,
    scopeMode: 'GLOBAL'|'FILTERED',
    month?: string|null,
    cutoffDate?: string|null,
    trackDate?: string|null,
  ): Observable<DatasetFreshness> {
    let params = new HttpParams()
      .set('module_key', moduleKey)
      .set('scope_mode', scopeMode);
    if (moduleKey === 'marketing.sales_funnel') {
      if (month) params = params.set('month', month);
      if (cutoffDate) params = params.set('cutoff_date', cutoffDate);
    } else if (trackDate) {
      params = params.set('track_date', trackDate);
    }
    return this.http.get<DatasetFreshness>(this.url, {params});
  }
}
