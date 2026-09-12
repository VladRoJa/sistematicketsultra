import { HttpClient, HttpParams } from '@angular/common/http';
import { Injectable } from '@angular/core';
import { Observable } from 'rxjs';

import { environment } from 'src/environments/environment';

import {
  MarketingSalesFunnelDetailResponse,
  MarketingSalesFunnelResponse,
} from './marketing-sales-funnel.models';


@Injectable({
  providedIn: 'root',
})
export class MarketingSalesFunnelService {
  private readonly apiUrl = `${environment.apiUrl}/marketing`;

  constructor(private readonly http: HttpClient) {}

  getDashboard(month: string): Observable<MarketingSalesFunnelResponse> {
    const params = new HttpParams().set('month', month);

    return this.http.get<MarketingSalesFunnelResponse>(
      `${this.apiUrl}/sales-funnel`,
      { params },
    );
  }

  getDetail(
    month: string,
    metric: string,
    branchId?: number,
    origin?: string,
    page = 1,
    pageSize = 50,
  ): Observable<MarketingSalesFunnelDetailResponse> {
    let params = new HttpParams()
      .set('month', month)
      .set('metric', metric)
      .set('page', page)
      .set('page_size', pageSize);

    if (branchId !== undefined) {
      params = params.set('branch_id', branchId);
    }
    if (origin) {
      params = params.set('origin', origin);
    }

    return this.http.get<MarketingSalesFunnelDetailResponse>(
      `${this.apiUrl}/sales-funnel/detail`,
      { params },
    );
  }
}
