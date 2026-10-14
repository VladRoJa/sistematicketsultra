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

export interface GoogleAdsM6StructuredResult {
  status: 'STRUCTURED_PAIR_STAGED' | 'ALREADY_INGESTED';
  business_date: string;
  campaign_upload_id: number;
  ad_group_upload_id: number;
  campaign_rows: number;
  group_rows: number;
  approval_version_id: number;
  account_cost_mxn: string;
  branch_cost_mxn: string;
  unassigned_cost_mxn: string;
  eligible_for_publication: false;
  funnel_publication: 'NOT_AUTHORIZED';
}

export interface GoogleAdsM6PublishedResult {
  status: 'CANONICAL_DAY_PUBLISHED' | 'ALREADY_PUBLISHED';
  publication_id: number;
  revision: number;
  business_date: string;
  customer_id: string;
  campaign_upload_id: number;
  ad_group_upload_id: number;
  approval_version_id: number;
  campaign_rows: number;
  group_rows: number;
  account_cost_mxn: string;
  branch_cost_mxn: string;
  unassigned_cost_mxn: string;
  is_canonical: true;
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

  ingest(campaignUploadId: number, groupUploadId: number): Observable<GoogleAdsM6StructuredResult> {
    return this.http.post<GoogleAdsM6StructuredResult>(
      `${this.url}/ingest`,
      {
        campaign_upload_id: campaignUploadId,
        ad_group_upload_id: groupUploadId,
        confirmation: 'INGESTAR_GOOGLE_ADS_M6_SIN_PUBLICAR'
      }
    );
  }

  publish(campaignUploadId: number, groupUploadId: number): Observable<GoogleAdsM6PublishedResult> {
    return this.http.post<GoogleAdsM6PublishedResult>(
      `${this.url}/publish`,
      {
        campaign_upload_id: campaignUploadId,
        ad_group_upload_id: groupUploadId,
        confirmation: 'PUBLICAR_GOOGLE_ADS_M6_DIA_CANONICO'
      }
    );
  }

  private pairForm(campaign: File, adGroup: File): FormData {
    const body = new FormData();
    body.append('campaign', campaign, campaign.name);
    body.append('ad_group', adGroup, adGroup.name);
    return body;
  }
}
