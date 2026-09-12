import { HttpClient, HttpParams } from '@angular/common/http';
import { Injectable } from '@angular/core';
import { Observable } from 'rxjs';

import { environment } from 'src/environments/environment';

import {
  MarketingSalesFunnelDetailResponse,
  MarketingSalesFunnelResponse,
  MarketingSalesFunnelSortDirection,
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
    sortBy?: string,
    sortDir: MarketingSalesFunnelSortDirection = 'asc',
  ): Observable<MarketingSalesFunnelDetailResponse> {
    const params = this.buildDetailParams(
      month,
      metric,
      branchId,
      origin,
      sortBy,
      sortDir,
    )
      .set('page', page)
      .set('page_size', pageSize);

    return this.http.get<MarketingSalesFunnelDetailResponse>(
      `${this.apiUrl}/sales-funnel/detail`,
      { params },
    );
  }

  exportDetail(
    month: string,
    metric: string,
    branchId?: number,
    origin?: string,
    sortBy?: string,
    sortDir: MarketingSalesFunnelSortDirection = 'asc',
  ): Observable<Blob> {
    const params = this.buildDetailParams(
      month,
      metric,
      branchId,
      origin,
      sortBy,
      sortDir,
    );

    return this.http.get(
      `${this.apiUrl}/sales-funnel/detail/export`,
      {
        params,
        responseType: 'blob',
      },
    );
  }

  private buildDetailParams(
    month: string,
    metric: string,
    branchId?: number,
    origin?: string,
    sortBy?: string,
    sortDir: MarketingSalesFunnelSortDirection = 'asc',
  ): HttpParams {
    let params = new HttpParams()
      .set('month', month)
      .set('metric', metric);

    if (branchId !== undefined) {
      params = params.set('branch_id', branchId);
    }
    if (origin) {
      params = params.set('origin', origin);
    }
    if (sortBy) {
      params = params
        .set('sort_by', sortBy)
        .set('sort_dir', sortDir);
    }

    return params;
  }
}
