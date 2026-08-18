import { HttpClient, HttpParams } from '@angular/common/http';
import { Injectable } from '@angular/core';
import { Observable } from 'rxjs';

import { environment } from 'src/environments/environment';

import {
  MarketingAttributionDetailResponse,
  MarketingDashboardResponse,
  MarketingInvestmentDetailResponse,
  MarketingInputPayload,
  MarketingInputsResponse,
  MarketingInputSaveResponse,
  MarketingLeadsDetailResponse,
  MarketingVisitorsDetailResponse,
} from './marketing.models';

@Injectable({
  providedIn: 'root',
})
export class MarketingService {
  private readonly apiUrl = `${environment.apiUrl}/marketing`;

  constructor(private readonly http: HttpClient) {}

  getDashboard(month: string): Observable<MarketingDashboardResponse> {
    const params = new HttpParams().set('month', month);

    return this.http.get<MarketingDashboardResponse>(
      `${this.apiUrl}/dashboard`,
      { params },
    );
  }

  getAttributions(
    month: string,
    branchId?: number,
  ): Observable<MarketingAttributionDetailResponse> {
    let params = new HttpParams().set('month', month);

    if (branchId !== undefined) {
      params = params.set('sucursal_id', String(branchId));
    }

    return this.http.get<MarketingAttributionDetailResponse>(
      `${this.apiUrl}/attributions`,
      { params },
    );
  }

  getInvestmentDetail(
    month: string,
    branchId?: number,
  ): Observable<MarketingInvestmentDetailResponse> {
    let params = new HttpParams().set('month', month);
    if (branchId !== undefined) {
      params = params.set('sucursal_id', String(branchId));
    }
    return this.http.get<MarketingInvestmentDetailResponse>(
      `${this.apiUrl}/investment-detail`,
      { params },
    );
  }

  getLeadsDetail(
    month: string,
    branchId?: number,
  ): Observable<MarketingLeadsDetailResponse> {
    let params = new HttpParams().set('month', month);
    if (branchId !== undefined) {
      params = params.set('sucursal_id', String(branchId));
    }
    return this.http.get<MarketingLeadsDetailResponse>(
      `${this.apiUrl}/leads-detail`,
      { params },
    );
  }

  getVisitorsDetail(
    month: string,
    branchId?: number,
  ): Observable<MarketingVisitorsDetailResponse> {
    let params = new HttpParams().set('month', month);
    if (branchId !== undefined) {
      params = params.set('sucursal_id', String(branchId));
    }
    return this.http.get<MarketingVisitorsDetailResponse>(
      `${this.apiUrl}/visitors-detail`,
      { params },
    );
  }

  getInputs(month: string): Observable<MarketingInputsResponse> {
    const params = new HttpParams().set('month', month);

    return this.http.get<MarketingInputsResponse>(
      `${this.apiUrl}/inputs`,
      { params },
    );
  }

  saveInput(
    branchId: number,
    payload: MarketingInputPayload,
  ): Observable<MarketingInputSaveResponse> {
    return this.http.put<MarketingInputSaveResponse>(
      `${this.apiUrl}/inputs/${branchId}`,
      payload,
    );
  }
}
