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
  CampaignV2BudgetRateRevision,
  CampaignV2ChannelPortfolioEvidence,
  CampaignV2ChannelPortfolioEvidenceRequest,
  CampaignV2PortfolioReviewResponse,
  CampaignV2ChannelPortfolioEvidenceResponse,
  CampaignV2PortfolioReference,
  CampaignV2PortfolioReferenceRequest,
  CampaignV2PortfolioReferencesResponse,
  CampaignV2QuotaEvidence,
  CampaignV2QuotaPolicyRevision,
  CampaignV2QuotaAttestation,
  CampaignV2QuotaPolicyRequest,
  CampaignV2QuotaAttestationRequest,
  CampaignV2BranchReview,
  CampaignV2PreviousContactReview,
  CampaignV2PreparationApplyResponse,
  CampaignV2PreparationApplyRequest,
  CampaignV2BudgetRateRequest,
  CampaignV2BudgetRatesResponse,
  CampaignV2DispatchTemplate,
  CampaignV2ChannelBinding,
  CampaignV2ChannelBindingRequest,
  CampaignV2ChannelBindingsResponse,
  CampaignV2CatalogBranchesResponse,
  CampaignV2TemplateConfigRequest,
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
  CampaignV2SubmitResponse,
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

  listDispatchTemplatesAdmin(): Observable<CampaignV2DispatchTemplatesResponse> {
    return this.http.get<CampaignV2DispatchTemplatesResponse>(
      `${this.apiUrl}/dispatch/templates/admin`,
    );
  }

  listDispatchChannelBindings(): Observable<CampaignV2ChannelBindingsResponse> {
    return this.http.get<CampaignV2ChannelBindingsResponse>(
      `${this.apiUrl}/dispatch/channel-bindings`,
    );
  }

  listDispatchCatalogBranches(): Observable<CampaignV2CatalogBranchesResponse> {
    return this.http.get<CampaignV2CatalogBranchesResponse>(
      `${this.apiUrl}/dispatch/catalog-branches`,
    );
  }

  createDispatchTemplate(request: CampaignV2TemplateConfigRequest): Observable<CampaignV2DispatchTemplate> {
    return this.http.post<CampaignV2DispatchTemplate>(
      `${this.apiUrl}/dispatch/templates`, request,
    );
  }

  updateDispatchTemplate(id: number, request: CampaignV2TemplateConfigRequest): Observable<CampaignV2DispatchTemplate> {
    return this.http.put<CampaignV2DispatchTemplate>(
      `${this.apiUrl}/dispatch/templates/${id}`, request,
    );
  }

  createDispatchChannelBinding(request: CampaignV2ChannelBindingRequest): Observable<CampaignV2ChannelBinding> {
    return this.http.post<CampaignV2ChannelBinding>(
      `${this.apiUrl}/dispatch/channel-bindings`, request,
    );
  }

  updateDispatchChannelBinding(id: number, request: CampaignV2ChannelBindingRequest): Observable<CampaignV2ChannelBinding> {
    return this.http.put<CampaignV2ChannelBinding>(
      `${this.apiUrl}/dispatch/channel-bindings/${id}`, request,
    );
  }

  listBudgetRateRevisions(templateId?: number): Observable<CampaignV2BudgetRatesResponse> {
    const params = templateId ? new HttpParams().set('template_id', String(templateId)) : undefined;
    return this.http.get<CampaignV2BudgetRatesResponse>(
      `${this.apiUrl}/dispatch/cost-rates`, { params },
    );
  }

  registerBudgetRateRevision(request: CampaignV2BudgetRateRequest): Observable<CampaignV2BudgetRateRevision> {
    return this.http.post<CampaignV2BudgetRateRevision>(
      `${this.apiUrl}/dispatch/cost-rates`, request,
    );
  }

  reviewAmbiguousBranches(campaignId: number, page = 1): Observable<CampaignV2BranchReview> {
    return this.http.get<CampaignV2BranchReview>(
      `${this.apiUrl}/${campaignId}/preparation/branches`,
      { params: new HttpParams().set('page', String(page)).set('page_size', '25') },
    );
  }

  applyAmbiguousBranches(
    campaignId: number, request: CampaignV2PreparationApplyRequest,
  ): Observable<CampaignV2PreparationApplyResponse> {
    return this.http.post<CampaignV2PreparationApplyResponse>(
      `${this.apiUrl}/${campaignId}/preparation/branches/exclude`, request,
    );
  }

  reviewPreviousContacts(
    campaignId: number, sourceCampaignIds: number[],
  ): Observable<CampaignV2PreviousContactReview> {
    return this.http.post<CampaignV2PreviousContactReview>(
      `${this.apiUrl}/${campaignId}/preparation/previous/review`,
      { source_campaign_ids: sourceCampaignIds },
    );
  }

  applyPreviousContacts(
    campaignId: number, sourceCampaignIds: number[],
    request: CampaignV2PreparationApplyRequest,
  ): Observable<CampaignV2PreparationApplyResponse> {
    return this.http.post<CampaignV2PreparationApplyResponse>(
      `${this.apiUrl}/${campaignId}/preparation/previous/exclude`,
      { ...request, source_campaign_ids: sourceCampaignIds },
    );
  }

  listPortfolioReview(): Observable<CampaignV2PortfolioReviewResponse> {
    return this.http.get<CampaignV2PortfolioReviewResponse>(
      `${this.apiUrl}/dispatch/portfolio-review`,
    );
  }

  listChannelPortfolioEvidence(): Observable<CampaignV2ChannelPortfolioEvidenceResponse> {
    return this.http.get<CampaignV2ChannelPortfolioEvidenceResponse>(
      `${this.apiUrl}/dispatch/channel-portfolio-evidence`,
    );
  }

  registerChannelPortfolioEvidence(
    request: CampaignV2ChannelPortfolioEvidenceRequest,
  ): Observable<CampaignV2ChannelPortfolioEvidence> {
    return this.http.post<CampaignV2ChannelPortfolioEvidence>(
      `${this.apiUrl}/dispatch/channel-portfolio-evidence`, request,
    );
  }

  listPortfolioReferences(): Observable<CampaignV2PortfolioReferencesResponse> {
    return this.http.get<CampaignV2PortfolioReferencesResponse>(
      `${this.apiUrl}/dispatch/portfolio-references`,
    );
  }

  registerPortfolioReference(
    request: CampaignV2PortfolioReferenceRequest,
  ): Observable<CampaignV2PortfolioReference> {
    return this.http.post<CampaignV2PortfolioReference>(
      `${this.apiUrl}/dispatch/portfolio-references`, request,
    );
  }

  listQuotaEvidence(): Observable<CampaignV2QuotaEvidence> {
    return this.http.get<CampaignV2QuotaEvidence>(
      `${this.apiUrl}/dispatch/quota-evidence`,
    );
  }

  registerQuotaPolicy(payload: CampaignV2QuotaPolicyRequest): Observable<CampaignV2QuotaPolicyRevision> {
    return this.http.post<CampaignV2QuotaPolicyRevision>(
      `${this.apiUrl}/dispatch/quota-policies`, payload,
    );
  }

  registerQuotaAttestation(payload: CampaignV2QuotaAttestationRequest): Observable<CampaignV2QuotaAttestation> {
    return this.http.post<CampaignV2QuotaAttestation>(
      `${this.apiUrl}/dispatch/quota-attestations`, payload,
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

  submitCampaign(
    campaignId: number,
    templateId: number,
    expectedDispatchFingerprint: string,
  ): Observable<CampaignV2SubmitResponse> {
    return this.http.post<CampaignV2SubmitResponse>(
      `${this.apiUrl}/${campaignId}/submit`,
      {
        template_id: templateId,
        expected_dispatch_fingerprint: expectedDispatchFingerprint,
      },
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
