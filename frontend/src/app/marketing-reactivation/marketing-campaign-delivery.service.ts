import { HttpClient, HttpParams } from '@angular/common/http';
import { Injectable } from '@angular/core';
import { Observable } from 'rxjs';

import { environment } from 'src/environments/environment';

import { ReactivationCampaignListResponse } from './marketing-reactivation.models';
import {
  CampaignDeliveryDetailResponse,
  CampaignDeliverySaveRequest,
  CampaignDeliverySummaryListResponse,
} from './marketing-campaign-delivery.models';

@Injectable({ providedIn: 'root' })
export class MarketingCampaignDeliveryService {
  private readonly apiUrl = `${environment.apiUrl}/marketing/reactivation/campaigns`;

  constructor(private readonly http: HttpClient) {}

  getCampaigns(): Observable<ReactivationCampaignListResponse> {
    return this.http.get<ReactivationCampaignListResponse>(this.apiUrl);
  }

  getDeliverySummaries(campaignIds: number[]): Observable<CampaignDeliverySummaryListResponse> {
    const params = new HttpParams().set('campaign_ids', campaignIds.join(','));
    return this.http.get<CampaignDeliverySummaryListResponse>(
      `${this.apiUrl}/delivery-summaries`,
      { params },
    );
  }

  getDelivery(campaignId: number): Observable<CampaignDeliveryDetailResponse> {
    return this.http.get<CampaignDeliveryDetailResponse>(
      `${this.apiUrl}/${campaignId}/delivery`,
    );
  }

  saveDelivery(
    campaignId: number,
    request: CampaignDeliverySaveRequest,
  ): Observable<CampaignDeliveryDetailResponse> {
    return this.http.post<CampaignDeliveryDetailResponse>(
      `${this.apiUrl}/${campaignId}/delivery`,
      request,
    );
  }
}
