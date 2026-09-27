import { HttpClient, HttpParams } from '@angular/common/http';
import { Injectable } from '@angular/core';
import { Observable } from 'rxjs';

import { environment } from '../../../environments/environment';
import {
  AttendanceBaseHealth,
  AttendanceBaseHealthMembersRequest,
  AttendanceBaseHealthMembersResponse,
  AttendanceBaseHealthRequest,
  AttendanceCatalogs,
  AttendanceDashboard,
  AttendanceDashboardRequest,
  AttendanceDetailRequest,
  AttendanceDetailResponse,
  SportsAnalysisContext,
} from './attendance.models';

@Injectable({ providedIn: 'root' })
export class AttendanceService {
  private readonly baseUrl = `${environment.apiUrl}/sports-analysis`;

  constructor(
    private readonly http: HttpClient,
  ) {}

  getContext(): Observable<SportsAnalysisContext> {
    return this.http.get<SportsAnalysisContext>(
      `${this.baseUrl}/context`,
    );
  }

  getCatalogs(): Observable<AttendanceCatalogs> {
    return this.http.get<AttendanceCatalogs>(
      `${this.baseUrl}/attendance/catalogs`,
    );
  }


  getDetail(
    request: AttendanceDetailRequest,
  ): Observable<AttendanceDetailResponse> {
    const params = this.buildDetailParams(request);
    return this.http.get<AttendanceDetailResponse>(
      `${this.baseUrl}/attendance/detail`,
      { params },
    );
  }

  exportDetail(
    request: AttendanceDetailRequest,
  ): Observable<Blob> {
    const params = this.buildDetailParams(request);
    return this.http.get(
      `${this.baseUrl}/attendance/detail/export`,
      {
        params,
        responseType: 'blob',
      },
    );
  }

  private buildDetailParams(
    request: AttendanceDetailRequest,
  ): HttpParams {
    let params = new HttpParams()
      .set('metric', request.metric)
      .set('date_from', request.dateFrom)
      .set('date_to', request.dateTo)
      .set('attendance_type', request.attendanceType);

    if (request.branchId !== null) {
      params = params.set(
        'branch_id',
        String(request.branchId),
      );
    }

    if (request.regionKey) {
      params = params.set(
        'region_key',
        request.regionKey,
      );
    }

    if (request.page !== undefined) {
      params = params.set(
        'page',
        String(request.page),
      );
    }

    if (request.pageSize !== undefined) {
      params = params.set(
        'page_size',
        String(request.pageSize),
      );
    }

    if (request.sortBy) {
      params = params.set(
        'sort_by',
        request.sortBy,
      );
    }

    if (request.sortDir) {
      params = params.set(
        'sort_dir',
        request.sortDir,
      );
    }

    if (request.minute !== undefined) {
      params = params.set(
        'minute',
        String(request.minute),
      );
    }

    if (request.hour !== undefined) {
      params = params.set(
        'hour',
        String(request.hour),
      );
    }

    if (request.ageBucket) {
      params = params.set(
        'age_bucket',
        request.ageBucket,
      );
    }

    return params;
  }

  getBaseHealth(
    filters: AttendanceBaseHealthRequest,
  ): Observable<AttendanceBaseHealth> {
    let params = new HttpParams()
      .set('date_from', filters.dateFrom)
      .set('date_to', filters.dateTo);

    if (filters.branchId !== null) {
      params = params.set(
        'branch_id',
        String(filters.branchId),
      );
    }

    if (filters.regionKey) {
      params = params.set(
        'region_key',
        filters.regionKey,
      );
    }

    return this.http.get<AttendanceBaseHealth>(
      `${this.baseUrl}/attendance/base-health`,
      { params },
    );
  }

  getBaseHealthMembers(
    request: AttendanceBaseHealthMembersRequest,
  ): Observable<AttendanceBaseHealthMembersResponse> {
    let params = new HttpParams()
      .set('date_from', request.dateFrom)
      .set('date_to', request.dateTo)
      .set('status', request.status);

    if (request.branchId !== null) {
      params = params.set(
        'branch_id',
        String(request.branchId),
      );
    }

    if (request.regionKey) {
      params = params.set(
        'region_key',
        request.regionKey,
      );
    }

    if (request.page !== undefined) {
      params = params.set(
        'page',
        String(request.page),
      );
    }

    if (request.pageSize !== undefined) {
      params = params.set(
        'page_size',
        String(request.pageSize),
      );
    }

    return this.http.get<AttendanceBaseHealthMembersResponse>(
      `${this.baseUrl}/attendance/base-health/members`,
      { params },
    );
  }

  getDashboard(
    filters: AttendanceDashboardRequest,
  ): Observable<AttendanceDashboard> {
    let params = new HttpParams()
      .set('date_from', filters.dateFrom)
      .set('date_to', filters.dateTo)
      .set('attendance_type', filters.attendanceType);

    if (filters.branchId !== null) {
      params = params.set(
        'branch_id',
        String(filters.branchId),
      );
    }

    if (filters.regionKey) {
      params = params.set(
        'region_key',
        filters.regionKey,
      );
    }

    return this.http.get<AttendanceDashboard>(
      `${this.baseUrl}/attendance/dashboard`,
      { params },
    );
  }
}
