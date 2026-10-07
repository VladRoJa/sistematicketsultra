import { HttpClient, HttpParams } from '@angular/common/http';
import { Injectable } from '@angular/core';
import { Observable } from 'rxjs';

import { environment } from 'src/environments/environment';

import {
  CampaignV2AudienceDefinitionRequest,
  CampaignV2BlacklistImportResult,
  CampaignV2BlacklistSummary,
  CampaignV2CampaignDetail,
  CampaignV2CampaignPage,
  CampaignV2CampaignQuery,
  CampaignV2ConsolidatedReport,
  CampaignV2DispatchTemplatesResponse,
  CampaignV2FreezeRequest,
  CampaignV2FreezeResponse,
  CampaignV2IndividualReport,
  CampaignV2OptionsResponse,
  CampaignV2PreflightResponse,
  CampaignV2PreviewDetailRequest,
  CampaignV2PreviewDetailResponse,
  CampaignV2PreviewResponse,
  CampaignV2Purpose,
  CampaignV2RecipientDetail,
  CampaignV2RecipientPage,
  CampaignV2ReportingFilters,
  CampaignV2TariffClassificationRequest,
  CampaignV2TariffClassificationResult,
  CampaignV2UnclassifiedTariffsResponse,
} from './marketing-campaign-v2.models';

@Injectable({
  providedIn: 'root',
})
export class MarketingCampaignV2Service {
  private readonly apiUrl = `${environment.apiUrl}/marketing/campaigns-v2`;

  constructor(private readonly http: HttpClient) {}

  getOptions(): Observable<CampaignV2OptionsResponse> {
    return this.http.get<CampaignV2OptionsResponse>(`${this.apiUrl}/options`);
  }

  getBlacklistSummary(): Observable<CampaignV2BlacklistSummary> {
    return this.http.get<CampaignV2BlacklistSummary>(`${this.apiUrl}/blacklist`);
  }

  importBlacklist(file: File): Observable<CampaignV2BlacklistImportResult> {
    const formData = new FormData();
    formData.append('file', file, file.name);
    return this.http.post<CampaignV2BlacklistImportResult>(
      `${this.apiUrl}/blacklist/import`,
      formData,
    );
  }

  exportBlacklist(): Observable<Blob> {
    return this.http.get(
      `${this.apiUrl}/blacklist/export`,
      { responseType: 'blob' },
    );
  }

  preview(request: CampaignV2AudienceDefinitionRequest): Observable<CampaignV2PreviewResponse> {
    return this.http.post<CampaignV2PreviewResponse>(`${this.apiUrl}/preview`, request);
  }

  previewDetail(
    request: CampaignV2PreviewDetailRequest,
  ): Observable<CampaignV2PreviewDetailResponse> {
    return this.http.post<CampaignV2PreviewDetailResponse>(
      `${this.apiUrl}/preview-detail`,
      request,
    );
  }

  freeze(request: CampaignV2FreezeRequest): Observable<CampaignV2FreezeResponse> {
    return this.http.post<CampaignV2FreezeResponse>(this.apiUrl, request);
  }

  listCampaigns(query: CampaignV2CampaignQuery): Observable<CampaignV2CampaignPage> {
    let params = new HttpParams()
      .set('page', String(query.page))
      .set('page_size', String(query.page_size));

    if (query.purpose) {
      params = params.set('purpose', query.purpose);
    }
    if (query.source) {
      params = params.set('source', query.source);
    }

    return this.http.get<CampaignV2CampaignPage>(this.apiUrl, { params });
  }

  getCampaign(campaignId: number): Observable<CampaignV2CampaignDetail> {
    return this.http.get<CampaignV2CampaignDetail>(`${this.apiUrl}/${campaignId}`);
  }

  listDispatchTemplates(
    purpose: CampaignV2Purpose,
  ): Observable<CampaignV2DispatchTemplatesResponse> {
    const params = new HttpParams().set('purpose', purpose);
    return this.http.get<CampaignV2DispatchTemplatesResponse>(
      `${this.apiUrl}/dispatch/templates`,
      { params },
    );
  }

  preflightCampaign(
    campaignId: number,
    templateId: number,
  ): Observable<CampaignV2PreflightResponse> {
    return this.http.post<CampaignV2PreflightResponse>(
      `${this.apiUrl}/${campaignId}/preflight`,
      { template_id: templateId },
    );
  }

  exportCampaignDeliveryPackage(campaignId: number): Observable<Blob> {
    return this.http.get(
      `${this.apiUrl}/${campaignId}/export-package`,
      { responseType: 'blob' },
    );
  }

  exportCampaignSendablePackage(campaignId: number): Observable<Blob> {
    return this.http.get(
      `${this.apiUrl}/${campaignId}/sendable-export-package`,
      { responseType: 'blob' },
    );
  }

  listRecipients(
    campaignId: number,
    page: number,
    pageSize: number,
  ): Observable<CampaignV2RecipientPage> {
    const params = new HttpParams()
      .set('page', String(page))
      .set('page_size', String(pageSize));

    return this.http.get<CampaignV2RecipientPage>(
      `${this.apiUrl}/${campaignId}/recipients`,
      { params },
    );
  }

  getRecipient(
    campaignId: number,
    recipientId: number,
  ): Observable<CampaignV2RecipientDetail> {
    return this.http.get<CampaignV2RecipientDetail>(
      `${this.apiUrl}/${campaignId}/recipients/${recipientId}`,
    );
  }

  listUnclassifiedTariffs(
    audience: CampaignV2AudienceDefinitionRequest,
  ): Observable<CampaignV2UnclassifiedTariffsResponse> {
    let params = new HttpParams().set('source', audience.source);
    if (audience.expiration_date_from) {
      params = params.set('expiration_date_from', audience.expiration_date_from);
    }
    if (audience.expiration_date_to) {
      params = params.set('expiration_date_to', audience.expiration_date_to);
    }
    return this.http.get<CampaignV2UnclassifiedTariffsResponse>(
      `${this.apiUrl}/tariffs/unclassified`,
      { params },
    );
  }

  classifyTariff(
    tarifaKey: string,
    request: CampaignV2TariffClassificationRequest,
    audience: CampaignV2AudienceDefinitionRequest,
  ): Observable<CampaignV2TariffClassificationResult> {
    let params = new HttpParams().set('source', audience.source);
    if (audience.expiration_date_from) {
      params = params.set('expiration_date_from', audience.expiration_date_from);
    }
    if (audience.expiration_date_to) {
      params = params.set('expiration_date_to', audience.expiration_date_to);
    }
    return this.http.put<CampaignV2TariffClassificationResult>(
      `${this.apiUrl}/tariffs/${encodeURIComponent(tarifaKey)}/classification`,
      request,
      { params },
    );
  }

  getCampaignReport(campaignId: number): Observable<CampaignV2IndividualReport> {
    return this.http.get<CampaignV2IndividualReport>(
      `${this.apiUrl}/${campaignId}/report`,
    );
  }

  getReporting(
    filters: CampaignV2ReportingFilters,
  ): Observable<CampaignV2ConsolidatedReport> {
    return this.http.get<CampaignV2ConsolidatedReport>(
      `${this.apiUrl}/reporting`,
      { params: this.buildReportingParams(filters) },
    );
  }

  exportReporting(filters: CampaignV2ReportingFilters): Observable<Blob> {
    return this.http.get(
      `${this.apiUrl}/reporting/export`,
      {
        params: this.buildReportingParams(filters),
        responseType: 'blob',
      },
    );
  }

  exportCampaignReport(campaignId: number): Observable<Blob> {
    const params = new HttpParams().set('campaign_id', String(campaignId));
    return this.http.get(
      `${this.apiUrl}/reporting/export`,
      {
        params,
        responseType: 'blob',
      },
    );
  }

  private buildReportingParams(
    filters: CampaignV2ReportingFilters,
  ): HttpParams {
    let params = new HttpParams();
    const entries: Array<[string, string | null | undefined]> = [
      ['observed_from', filters.observed_from],
      ['observed_to', filters.observed_to],
      ['purpose', filters.purpose],
      ['source', filters.source],
      ['provider', filters.provider],
      ['snapshot_status', filters.snapshot_status],
    ];
    for (const [key, value] of entries) {
      if (value !== null && value !== undefined && value !== '') {
        params = params.set(key, value);
      }
    }
    return params;
  }

  updatePurpose(
    campaignId: number,
    purpose: CampaignV2Purpose,
  ): Observable<CampaignV2CampaignDetail> {
    return this.http.patch<CampaignV2CampaignDetail>(
      `${this.apiUrl}/${campaignId}/purpose`,
      { purpose },
    );
  }
}
