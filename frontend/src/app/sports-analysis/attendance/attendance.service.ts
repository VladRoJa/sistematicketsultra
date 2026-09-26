import { HttpClient, HttpParams } from '@angular/common/http';
import { Injectable } from '@angular/core';
import { Observable } from 'rxjs';

import { environment } from '../../../environments/environment';
import {
  AttendanceCatalogs,
  AttendanceDashboard,
  AttendanceDashboardRequest,
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
