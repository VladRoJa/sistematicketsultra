import { HttpClient, HttpParams, HttpResponse } from '@angular/common/http';
import { Injectable } from '@angular/core';
import { Observable } from 'rxjs';
import { environment } from '../../../environments/environment';
import {
  RoutineControlCatalogs,
  RoutineControlCreateNoRoutineDecisionRequest,
  RoutineControlDecisionMutationResponse,
  RoutineControlFilters,
  RoutineControlMemberDetail,
  RoutineControlMembersResponse,
  RoutineControlRevokeNoRoutineDecisionRequest,
  RoutineControlRunFilters,
  RoutineControlRunsResponse,
  RoutineControlSummary,
} from '../models/routine-control.models';

@Injectable({ providedIn: 'root' })
export class RoutineControlService {
  private readonly baseUrl = `${environment.apiUrl}/routine-control`;

  constructor(private readonly http: HttpClient) {}

  getCatalogs(
    filters: Partial<RoutineControlFilters> = {},
  ): Observable<RoutineControlCatalogs> {
    return this.http.get<RoutineControlCatalogs>(
      `${this.baseUrl}/catalogs`,
      {
        params: this.paramsFromRecord({
          ...filters,
        }),
      },
    );
  }

  getSummary(filters: RoutineControlFilters): Observable<RoutineControlSummary> {
    return this.http.get<RoutineControlSummary>(`${this.baseUrl}/summary`, {
      params: this.memberParams(filters, false),
    });
  }

  getMembers(filters: RoutineControlFilters): Observable<RoutineControlMembersResponse> {
    return this.http.get<RoutineControlMembersResponse>(`${this.baseUrl}/members`, {
      params: this.memberParams(filters, true),
    });
  }

  getMemberDetail(id: number): Observable<RoutineControlMemberDetail> {
    return this.http.get<RoutineControlMemberDetail>(
      `${this.baseUrl}/members/${id}`,
    );
  }

  createNoRoutineDecision(
    memberId: number,
    payload: RoutineControlCreateNoRoutineDecisionRequest,
  ): Observable<RoutineControlDecisionMutationResponse> {
    return this.http.post<RoutineControlDecisionMutationResponse>(
      `${this.baseUrl}/members/${memberId}/no-routine-decision`,
      payload,
    );
  }

  revokeNoRoutineDecision(
    memberId: number,
    decisionId: number,
    payload: RoutineControlRevokeNoRoutineDecisionRequest,
  ): Observable<RoutineControlDecisionMutationResponse> {
    return this.http.post<RoutineControlDecisionMutationResponse>(
      `${this.baseUrl}/members/${memberId}/no-routine-decision/${decisionId}/revoke`,
      payload,
    );
  }

  getRuns(filters: RoutineControlRunFilters): Observable<RoutineControlRunsResponse> {
    return this.http.get<RoutineControlRunsResponse>(`${this.baseUrl}/runs`, {
      params: this.paramsFromRecord({ ...filters }),
    });
  }

  exportMembers(filters: RoutineControlFilters): Observable<HttpResponse<Blob>> {
    return this.http.get(`${this.baseUrl}/members/export`, {
      params: this.memberParams(filters, false),
      responseType: 'blob',
      observe: 'response',
    });
  }

  downloadExport(response: HttpResponse<Blob>): void {
    if (!response.body) return;
    const disposition = response.headers.get('Content-Disposition') || '';
    const filenameMatch = disposition.match(/filename\*?=(?:UTF-8''|\")?([^\";]+)/i);
    const filename = filenameMatch?.[1] ? decodeURIComponent(filenameMatch[1].replace(/\"/g, '')) : 'control_rutinas.xlsx';
    const objectUrl = URL.createObjectURL(response.body);
    const anchor = document.createElement('a');
    anchor.href = objectUrl;
    anchor.download = filename;
    anchor.click();
    URL.revokeObjectURL(objectUrl);
  }

  private memberParams(filters: RoutineControlFilters, includePagination: boolean): HttpParams {
    const values: Record<string, string | number | null | undefined> = { ...filters };
    if (!includePagination) {
      delete values['page'];
      delete values['page_size'];
    }
    return this.paramsFromRecord(values);
  }

  private paramsFromRecord(values: Record<string, string | number | null | undefined>): HttpParams {
    let params = new HttpParams();
    Object.entries(values).forEach(([key, value]) => {
      if (value !== null && value !== undefined && value !== '') {
        params = params.set(key, String(value));
      }
    });
    return params;
  }
}
