import { HttpClient, HttpParams } from '@angular/common/http';
import { Injectable } from '@angular/core';
import { Observable } from 'rxjs';

import { environment } from 'src/environments/environment';

import {
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

@Injectable({
  providedIn: 'root',
})
export class MarketingReactivationService {
  private readonly apiUrl = `${environment.apiUrl}/marketing/reactivation`;

  constructor(private readonly http: HttpClient) {}

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

  previewCampaign(
    request: ReactivationCampaignRequest,
  ): Observable<ReactivationCampaignPreviewResponse> {
    return this.http.post<ReactivationCampaignPreviewResponse>(
      `${this.apiUrl}/campaigns/preview`,
      request,
    );
  }

  createCampaign(
    request: ReactivationCampaignRequest,
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
    return this.http.get(`${this.apiUrl}/campaigns/${id}/export`, {
      responseType: 'blob',
    });
  }

  markCampaignSent(id: number): Observable<ReactivationCampaignResponse> {
    return this.http.post<ReactivationCampaignResponse>(
      `${this.apiUrl}/campaigns/${id}/mark-sent`,
      {},
    );
  }
}
