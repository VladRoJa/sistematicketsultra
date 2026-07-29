import { HttpClient, HttpParams } from '@angular/common/http';
import { Injectable } from '@angular/core';
import { Observable } from 'rxjs';

import { environment } from 'src/environments/environment';

import {
  MarketingDashboardResponse,
  MarketingInputPayload,
  MarketingInputsResponse,
  MarketingInputSaveResponse,
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
