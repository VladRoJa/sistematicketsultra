import { HttpClient, HttpParams } from '@angular/common/http';
import { Injectable } from '@angular/core';
import { Observable } from 'rxjs';

import { environment } from 'src/environments/environment';

import {
  MarketingSalesFunnelDetailResponse,
  MarketingSalesFunnelResponse,
  MarketingSalesFunnelSortDirection,
} from './marketing-sales-funnel.models';

export type MarketingSalesFunnelCutoffPolicy =
  | 'exact'
  | 'latest_available_at_or_before';


@Injectable({
  providedIn: 'root',
})
export class MarketingSalesFunnelOriginalService {
  private readonly apiUrl = `${environment.apiUrl}/marketing`;

  constructor(private readonly http: HttpClient) {}

  getDashboard(
    month: string,
    branchIds: number[] = [],
    cutoffDate?: string | null,
    cutoffPolicy: MarketingSalesFunnelCutoffPolicy = 'exact',
  ): Observable<MarketingSalesFunnelResponse> {
    let params = new HttpParams()
      .set('month', month)
      .set('visit_mode', 'registered_only');
    if (cutoffDate) {
      params = params.set('cutoff_date', cutoffDate);
    }
    if (cutoffPolicy !== 'exact') {
      params = params.set('cutoff_policy', cutoffPolicy);
    }
    params = this.withBranchIds(params, branchIds);

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
    branchIds: number[] = [],
    cutoffDate?: string | null,
  ): Observable<MarketingSalesFunnelDetailResponse> {
    let params = this.buildDetailParams(
      month,
      metric,
      branchId,
      origin,
      sortBy,
      sortDir,
      branchIds,
    )
      .set('page', page)
      .set('page_size', pageSize);

    if (cutoffDate) {
      params = params.set('cutoff_date', cutoffDate);
    }

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
    branchIds: number[] = [],
    cutoffDate?: string | null,
  ): Observable<Blob> {
    let params = this.buildDetailParams(
      month,
      metric,
      branchId,
      origin,
      sortBy,
      sortDir,
      branchIds,
    );
    if (cutoffDate) {
      params = params.set('cutoff_date', cutoffDate);
    }

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
    branchIds: number[] = [],
  ): HttpParams {
    let params = new HttpParams()
      .set('month', month)
      .set('metric', metric)
      .set('visit_mode', 'registered_only');

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

    return this.withBranchIds(params, branchIds);
  }

  private withBranchIds(params: HttpParams, branchIds: number[]): HttpParams {
    if (!branchIds.length) {
      return params;
    }
    return params.set('branch_ids', branchIds.join(','));
  }
}
