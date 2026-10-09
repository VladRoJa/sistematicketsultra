import { HttpClient, HttpParams } from '@angular/common/http';
import { Injectable } from '@angular/core';
import { Observable } from 'rxjs';

import { environment } from '../../environments/environment';
import {
  SystemDailyCheckBiContext,
  SystemDailyCheckDetail,
  SystemDailyCheckFilters,
  SystemDailyCheckGeneralStatus,
  SystemDailyCheckGranularity,
  SystemDailyCheckHistory,
  SystemDailyCheckIssuesDrilldown,
  SystemDailyCheckMatrix,
  SystemDailyCheckPending,
  SystemDailyCheckSummary,
  SystemDailyCheckTrends,
  SystemDailyCheckUniverse,
} from './system-daily-check-bi.models';

@Injectable({ providedIn: 'root' })
export class SystemDailyCheckBiService {
  private readonly baseUrl =
    `${environment.apiUrl}/system-daily-checks/bi`;

  constructor(
    private readonly http: HttpClient,
  ) {}

  getContext(): Observable<SystemDailyCheckBiContext> {
    return this.http.get<SystemDailyCheckBiContext>(
      `${this.baseUrl}/context`,
    );
  }

  getSummary(
    filters: SystemDailyCheckFilters,
  ): Observable<SystemDailyCheckSummary> {
    return this.http.get<SystemDailyCheckSummary>(
      `${this.baseUrl}/summary`,
      { params: this.buildRangeParams(filters) },
    );
  }

  exportExcel(filters: SystemDailyCheckFilters): Observable<Blob> {
    return this.http.get(
      `${this.baseUrl}/export.xlsx`,
      {
        params: this.buildRangeParams(filters),
        responseType: 'blob',
      },
    );
  }

  getMatrix(
    businessDate: string,
    branchId: number | null,
  ): Observable<SystemDailyCheckMatrix> {
    let params = new HttpParams().set('date', businessDate);
    if (branchId !== null) {
      params = params.set('branch_id', String(branchId));
    }
    return this.http.get<SystemDailyCheckMatrix>(
      `${this.baseUrl}/matrix`,
      { params },
    );
  }

  getTrends(
    filters: SystemDailyCheckFilters,
    granularity: SystemDailyCheckGranularity,
  ): Observable<SystemDailyCheckTrends> {
    let params = this.buildRangeParams(filters)
      .set('granularity', granularity);
    return this.http.get<SystemDailyCheckTrends>(
      `${this.baseUrl}/trends`,
      { params },
    );
  }

  getHistory(
    filters: SystemDailyCheckFilters,
    options: {
      generalStatus?: SystemDailyCheckGeneralStatus | null;
      questionKey?: string | null;
      answer?: 'YES' | 'NO' | 'NA' | null;
      page?: number;
      pageSize?: number;
    } = {},
  ): Observable<SystemDailyCheckHistory> {
    let params = this.buildRangeParams(filters);

    if (options.generalStatus) {
      params = params.set(
        'general_status',
        options.generalStatus,
      );
    }
    if (options.questionKey) {
      params = params.set(
        'question_key',
        options.questionKey,
      );
    }
    if (options.answer) {
      params = params.set('answer', options.answer);
    }
    params = params
      .set('page', String(options.page ?? 1))
      .set('page_size', String(options.pageSize ?? 50));

    return this.http.get<SystemDailyCheckHistory>(
      `${this.baseUrl}/history`,
      { params },
    );
  }

  getPending(
    filters: SystemDailyCheckFilters,
    page = 1,
    pageSize = 50,
  ): Observable<SystemDailyCheckPending> {
    let params = this.buildRangeParams(filters)
      .set('page', String(page))
      .set('page_size', String(pageSize));

    return this.http.get<SystemDailyCheckPending>(
      `${this.baseUrl}/pending`,
      { params },
    );
  }



  getIssues(
    filters: SystemDailyCheckFilters,
    reportedToSupport: boolean | null,
    questionKey: string | null = null,
  ): Observable<SystemDailyCheckIssuesDrilldown> {
    let params = this.buildRangeParams(filters)
      .set('page', '1')
      .set('page_size', '200');

    if (reportedToSupport !== null) {
      params = params.set(
        'reported_to_support',
        String(reportedToSupport),
      );
    }
    if (questionKey) {
      params = params.set('question_key', questionKey);
    }

    return this.http.get<SystemDailyCheckIssuesDrilldown>(
      `${this.baseUrl}/issues`,
      { params },
    );
  }

  getDetail(
    checkId: number,
  ): Observable<SystemDailyCheckDetail> {
    return this.http.get<SystemDailyCheckDetail>(
      `${this.baseUrl}/checks/${checkId}`,
    );
  }

  getAttachment(
    attachmentId: number,
  ): Observable<Blob> {
    return this.http.get(
      `${this.baseUrl}/attachments/${attachmentId}`,
      { responseType: 'blob' },
    );
  }

  replaceRollout(
    branchIds: number[],
  ): Observable<{
    allowed: boolean;
    universe: SystemDailyCheckUniverse;
  }> {
    return this.http.put<{
      allowed: boolean;
      universe: SystemDailyCheckUniverse;
    }>(
      `${this.baseUrl}/rollout`,
      { branch_ids: branchIds },
    );
  }

  private buildRangeParams(
    filters: SystemDailyCheckFilters,
  ): HttpParams {
    let params = new HttpParams()
      .set('date_from', filters.dateFrom)
      .set('date_to', filters.dateTo);

    if (filters.branchId !== null) {
      params = params.set(
        'branch_id',
        String(filters.branchId),
      );
    }

    return params;
  }
}
