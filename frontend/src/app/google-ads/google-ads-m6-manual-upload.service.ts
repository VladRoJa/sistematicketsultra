import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';
import { environment } from 'src/environments/environment';

export interface GoogleAdsM6ManualPreview {
  status: 'PREFLIGHT_OK';
  business_date: string;
  customer_id: string;
  campaign_rows: number;
  group_rows: number;
  approved_branches: number;
  account_cost_mxn: string;
  branch_cost_mxn: string;
  unassigned_cost_mxn: string;
  campaign_sha256: string;
  ad_group_sha256: string;
  raw_confirm_ticket: string;
  ready_to_stage_raw: boolean;
  initial_m6_approval_verified: false;
  eligible_for_structured_ingestion: false;
  eligible_for_publication: false;
}

export interface GoogleAdsM6RawUpload {
  upload_id: number;
  file_hash_sha256: string;
  reused_existing: boolean;
}

export interface GoogleAdsM6RawResult {
  status: 'RAW_PAIR_STAGED' | 'PARTIAL_RAW' | 'RAW_STAGE_FAILED';
  business_date: string;
  uploads: Record<string, GoogleAdsM6RawUpload>;
  code?: string;
  account_cost_mxn?: string;
  branch_cost_mxn?: string;
  unassigned_cost_mxn?: string;
  initial_m6_approval_verified?: false;
  eligible_for_structured_ingestion: false;
  eligible_for_publication: false;
}

@Injectable({ providedIn: 'root' })
export class GoogleAdsM6ManualUploadService {
  private readonly url = `${environment.apiUrl}/integrations/google-ads/manual`;

  constructor(private readonly http: HttpClient) {}

  preview(campaign: File, adGroup: File): Observable<GoogleAdsM6ManualPreview> {
    return this.http.post<GoogleAdsM6ManualPreview>(
      `${this.url}/preview`, this.pairForm(campaign, adGroup)
    );
  }

  confirm(
    campaign: File, adGroup: File, confirmationTicket: string
  ): Observable<GoogleAdsM6RawResult> {
    const body = this.pairForm(campaign, adGroup);
    body.append('confirmation_ticket', confirmationTicket);
    return this.http.post<GoogleAdsM6RawResult>(`${this.url}/confirm`, body);
  }

  private pairForm(campaign: File, adGroup: File): FormData {
    const body = new FormData();
    body.append('campaign', campaign, campaign.name);
    body.append('ad_group', adGroup, adGroup.name);
    return body;
  }
}
