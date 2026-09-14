import { HttpClient, HttpParams } from '@angular/common/http';
import { Injectable } from '@angular/core';
import { Observable } from 'rxjs';

import { environment } from 'src/environments/environment';

import {
  CampaignAudienceCreateRequest,
  CampaignAudienceCreateResponse,
  CampaignAudienceSelectionRequest,
  CampaignAudienceSelectionResponse,
} from './marketing-audience-explorer.models';
import {
  CampaignAudiencePreviewDetailRequest,
  CampaignAudiencePreviewDetailResponse,
  CampaignOptions,
  CampaignV1Request,
  ReactivationCampaignDetailResponse,
  ReactivationCampaignListResponse,
  ReactivationCampaignPreviewResponse,
  ReactivationCampaignRequest,
  ReactivationCampaignResponse,
  ReactivationCandidateQuery,
  ReactivationCandidateSummaryQuery,
  ReactivationCandidateSummaryResponse,
  ReactivationCandidatesResponse,
  ReactivationSourcesResponse,
  ReactivationTariffsResponse,
} from './marketing-reactivation.models';
import {
  ReactivationCampaignOutcomeDetailResponse,
  ReactivationOutcomeSummaryResponse,
} from './marketing-reactivation-outcome.models';
import { CampaignSourceStatusResponse } from './marketing-campaign-source-status.models';

@Injectable({
  providedIn: 'root',
})
export class MarketingReactivationService {
  private readonly apiUrl = `${environment.apiUrl}/marketing/reactivation`;

  constructor(private readonly http: HttpClient) {}

  getCampaignOptions(): Observable<CampaignOptions> {
    return this.http.get<CampaignOptions>(`${this.apiUrl}/campaigns/options`);
  }

  getCampaignSourceStatus(): Observable<CampaignSourceStatusResponse> {
    return this.http.get<CampaignSourceStatusResponse>(
      `${this.apiUrl}/campaigns/source-status`,
    );
  }

  getSources(): Observable<ReactivationSourcesResponse> {
    return this.http.get<ReactivationSourcesResponse>(
      `${this.apiUrl}/sources`,
    );
  }

  getCandidates(
    query: ReactivationCandidateQuery,
  ): Observable<ReactivationCandidatesResponse> {
    let params = new HttpParams()
      .set('date_from', query.dateFrom)
      .set('date_to', query.dateTo)
      .set('iventas_period_key', query.iventasPeriodKey)
      .set('page', String(query.page))
      .set('page_size', String(query.pageSize))
      .set('operational_status', query.operationalStatus)
      .set('sort', query.sort)
      .set('direction', query.direction);
    if (query.sucursal) {
      params = params.set('sucursal', query.sucursal);
    }
    if (query.tarifa) {
      params = params.set('tarifa', query.tarifa);
    }
    if (query.tariffCategory) {
      params = params.set('tariff_category', query.tariffCategory);
    }
    if (query.tariffGroup) {
      params = params.set('tariff_group', query.tariffGroup);
    }
    if (query.search) {
      params = params.set('search', query.search);
    }
    if (query.cursor) {
      params = params.set('cursor', query.cursor);
    }

    return this.http.get<ReactivationCandidatesResponse>(
      `${this.apiUrl}/candidates`,
      { params },
    );
  }

  getCandidateSummary(
    query: ReactivationCandidateSummaryQuery,
  ): Observable<ReactivationCandidateSummaryResponse> {
    let params = new HttpParams()
      .set('date_from', query.dateFrom)
      .set('date_to', query.dateTo)
      .set('iventas_period_key', query.iventasPeriodKey)
      .set('operational_status', query.operationalStatus);
    if (query.sucursal) {
      params = params.set('sucursal', query.sucursal);
    }
    if (query.tarifa) {
      params = params.set('tarifa', query.tarifa);
    }
    if (query.tariffCategory) {
      params = params.set('tariff_category', query.tariffCategory);
    }
    if (query.tariffGroup) {
      params = params.set('tariff_group', query.tariffGroup);
    }
    if (query.search) {
      params = params.set('search', query.search);
    }
    return this.http.get<ReactivationCandidateSummaryResponse>(
      `${this.apiUrl}/candidates/summary`,
      { params },
    );
  }

  getTariffs(
    dateFrom: string,
    dateTo: string,
  ): Observable<ReactivationTariffsResponse> {
    const params = new HttpParams()
      .set('date_from', dateFrom)
      .set('date_to', dateTo);
    return this.http.get<ReactivationTariffsResponse>(
      `${this.apiUrl}/tariffs`,
      { params },
    );
  }

  exportSelection(
    request: ReactivationCampaignRequest,
  ): Observable<Blob> {
    return this.http.post(`${this.apiUrl}/candidates/export`, request, {
      responseType: 'blob',
    });
  }

  previewCampaign(
    request: ReactivationCampaignRequest | CampaignV1Request,
  ): Observable<ReactivationCampaignPreviewResponse> {
    return this.http.post<ReactivationCampaignPreviewResponse>(
      `${this.apiUrl}/campaigns/preview`,
      request,
    );
  }

  previewCampaignDetail(
    request: CampaignAudiencePreviewDetailRequest,
  ): Observable<CampaignAudiencePreviewDetailResponse> {
    return this.http.post<CampaignAudiencePreviewDetailResponse>(
      `${this.apiUrl}/campaigns/preview-detail`,
      request,
    );
  }

  previewExplorerCampaignSelection(
    request: CampaignAudienceSelectionRequest,
  ): Observable<CampaignAudienceSelectionResponse> {
    return this.http.post<CampaignAudienceSelectionResponse>(
      `${this.apiUrl}/campaigns/preview-detail/selection`,
      request,
    );
  }

  createCampaignFromExplorer(
    request: CampaignAudienceCreateRequest,
  ): Observable<CampaignAudienceCreateResponse> {
    return this.http.post<CampaignAudienceCreateResponse>(
      `${this.apiUrl}/campaigns/preview-detail/create`,
      request,
    );
  }

  createCampaign(
    request: ReactivationCampaignRequest | CampaignV1Request,
  ): Observable<ReactivationCampaignResponse> {
    return this.http.post<ReactivationCampaignResponse>(
      `${this.apiUrl}/campaigns`,
      request,
    );
  }

  getCampaigns(): Observable<ReactivationCampaignListResponse> {
    return this.http.get<ReactivationCampaignListResponse>(
      `${this.apiUrl}/campaigns`,
    );
  }

  getCampaign(id: number): Observable<ReactivationCampaignDetailResponse> {
    return this.http.get<ReactivationCampaignDetailResponse>(
      `${this.apiUrl}/campaigns/${id}`,
    );
  }

  exportCampaign(id: number): Observable<Blob> {
    return this.http.get(`${this.apiUrl}/campaigns/${id}/export-package`, {
      responseType: 'blob',
    });
  }

  markCampaignSent(id: number): Observable<ReactivationCampaignResponse> {
    return this.http.post<ReactivationCampaignResponse>(
      `${this.apiUrl}/campaigns/${id}/mark-sent`,
      {},
    );
  }

  getOutcomeSummary(filters: {
    dateFrom?: string | null;
    dateTo?: string | null;
    regionId?: number | null;
    sucursal?: string | null;
  } = {}): Observable<ReactivationOutcomeSummaryResponse> {
    let params = new HttpParams();
    if (filters.dateFrom) params = params.set('date_from', filters.dateFrom);
    if (filters.dateTo) params = params.set('date_to', filters.dateTo);
    if (filters.regionId !== null && filters.regionId !== undefined) {
      params = params.set('region_id', String(filters.regionId));
    }
    if (filters.sucursal) params = params.set('sucursal', filters.sucursal);
    return this.http.get<ReactivationOutcomeSummaryResponse>(
      `${this.apiUrl}/outcomes/summary`,
      { params },
    );
  }

  getCampaignOutcomes(id: number): Observable<ReactivationCampaignOutcomeDetailResponse> {
    return this.http.get<ReactivationCampaignOutcomeDetailResponse>(
      `${this.apiUrl}/outcomes/campaigns/${id}`,
    );
  }

  refreshOutcomes(): Observable<Record<string, unknown>> {
    return this.http.post<Record<string, unknown>>(
      `${this.apiUrl}/outcomes/run`,
      {},
    );
  }
}
