import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';
import { environment } from 'src/environments/environment';

export interface M6CorrectionCapabilities {
  can_read: boolean;
  can_stage_raw: boolean;
  can_ingest: boolean;
  can_review: boolean;
  can_promote: boolean;
}

export interface M6CorrectionCaseSummary {
  case_id: number;
  business_date: string;
  revision: number;
  decision: 'PENDING' | 'APPROVED' | 'REJECTED';
}

export interface M6CorrectionCase {
  case_id: number;
  business_date: string;
  revision: number;
  expected_publication_id: number | null;
  campaign_rows: number;
  group_rows: number;
  reason: string;
  candidate_account_cost_mxn: string;
  candidate_assigned_cost_mxn: string;
  candidate_unassigned_cost_mxn: string;
  previous_account_cost_mxn: string | null;
  delta_account_cost_mxn: string | null;
  branch_costs_mxn: { sucursal_canon: string; cost_mxn: string }[];
  status: string;
  approved: boolean;
  decision: {
    decision_id: number;
    decision: 'APPROVED' | 'REJECTED';
    reviewed_by_user_id: number;
    snapshot_sha256: string;
  } | null;
  promotion: {
    publication_id: number;
    promoted_by_user_id: number;
  } | null;
  eligible_for_publication: false;
}

export interface M6CorrectionPreview {
  status: 'CORRECTION_PREFLIGHT_OK';
  correction_ticket: string;
  business_date: string;
  revision: number;
  expected_publication_id: number | null;
  account_cost_mxn: string;
  branch_cost_mxn: string;
  unassigned_cost_mxn: string;
  campaign_rows: number;
  group_rows: number;
}

export interface M6CorrectionRawPair {
  status: 'CORRECTION_RAW_PAIR_STAGED' | 'PARTIAL_RAW' | 'RAW_STAGE_FAILED';
  uploads: Record<string, {
    upload_id: number;
    file_hash_sha256: string;
    reused_existing: boolean;
  }>;
  eligible_for_publication: false;
}

export interface M6CorrectionCandidateResult {
  status: 'CANDIDATE_STAGED' | 'ALREADY_STAGED';
  case_id: number;
  revision: number;
  business_date: string;
  campaign_rows: number;
  group_rows: number;
  eligible_for_publication: false;
}

export interface M6CorrectionDecisionResult {
  decision_id: number;
  case_id: number;
  decision: 'APPROVED' | 'REJECTED';
  snapshot_sha256: string;
  status: 'REVIEW_RECORDED' | 'ALREADY_REVIEWED';
  eligible_for_publication: false;
}

export interface M6CorrectionPromotionResult {
  status: 'CORRECTION_CANONICAL_PROMOTED' | 'ALREADY_PROMOTED';
  publication_id: number;
  case_id: number;
  revision: number;
  business_date: string;
  account_cost_mxn: string;
  is_canonical: true;
}

@Injectable({ providedIn: 'root' })
export class GoogleAdsM6CorrectionWorkbenchService {
  private readonly base = `${environment.apiUrl}/integrations/google-ads/corrections`;

  constructor(private readonly http: HttpClient) {}

  capabilities(): Observable<M6CorrectionCapabilities> {
    return this.http.get<M6CorrectionCapabilities>(`${this.base}/capabilities`);
  }

  listCases(): Observable<{ cases: M6CorrectionCaseSummary[] }> {
    return this.http.get<{ cases: M6CorrectionCaseSummary[] }>(`${this.base}/candidates`);
  }

  inspectCase(caseId: number): Observable<M6CorrectionCase> {
    return this.http.get<M6CorrectionCase>(`${this.base}/candidates/${caseId}`);
  }

  preview(campaign: File, groups: File, reason: string): Observable<M6CorrectionPreview> {
    const data = this.files(campaign, groups);
    data.append('reason', reason);
    return this.http.post<M6CorrectionPreview>(`${this.base}/raw/preview`, data);
  }

  confirm(campaign: File, groups: File, ticket: string): Observable<M6CorrectionRawPair> {
    const data = this.files(campaign, groups);
    data.append('correction_ticket', ticket);
    return this.http.post<M6CorrectionRawPair>(`${this.base}/raw/confirm`, data);
  }

  stage(raw: M6CorrectionRawPair, preview: M6CorrectionPreview, reason: string):
    Observable<M6CorrectionCandidateResult> {
    return this.http.post<M6CorrectionCandidateResult>(
      `${this.base}/candidates/ingest`, {
        campaign_upload_id: raw.uploads['google_ads_campaign_daily'].upload_id,
        ad_group_upload_id: raw.uploads['google_ads_ad_group_daily'].upload_id,
        revision: preview.revision,
        expected_publication_id: preview.expected_publication_id,
        reason,
        confirmation: 'INGESTAR_CORRECCION_M6_SIN_PUBLICAR'
      }
    );
  }

  review(caseId: number, decision: 'APPROVED' | 'REJECTED', note: string):
    Observable<M6CorrectionDecisionResult> {
    return this.http.post<M6CorrectionDecisionResult>(
      `${this.base}/candidates/${caseId}/review`, {
        decision, note, confirmation: 'REVISION_INDEPENDIENTE_SIN_PUBLICAR'
      }
    );
  }

  promote(data: M6CorrectionCase): Observable<M6CorrectionPromotionResult> {
    if (!data.decision) throw new Error('No existe revisión independiente');
    return this.http.post<M6CorrectionPromotionResult>(
      `${this.base}/candidates/${data.case_id}/promote`, {
        decision_id: data.decision.decision_id,
        snapshot_sha256: data.decision.snapshot_sha256,
        revision: data.revision,
        expected_publication_id: data.expected_publication_id,
        confirmation: 'PUBLICAR_REVISION_GOOGLE_ADS_M6'
      }
    );
  }

  private files(campaign: File, groups: File): FormData {
    const data = new FormData();
    data.append('campaign', campaign, campaign.name);
    data.append('ad_group', groups, groups.name);
    return data;
  }
}
