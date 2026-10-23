import { HttpClient, HttpParams } from '@angular/common/http';
import { Injectable } from '@angular/core';
import { Observable } from 'rxjs';
import { environment } from 'src/environments/environment';

export type AuditPerspective = 'user' | 'module' | 'action';
export type AuditComparison = 'coincide' | 'diferencia' | 'no_concluyente';

export interface VisualAuditRow {
  user_id: number;
  username: string;
  role: string;
  primary_branch_id: number | null;
  branch_ids: number[];
  action_id: number | null;
  action_key: string | null;
  action_name: string;
  module_key: string;
  module_name: string;
  module_entry: boolean;
  legacy_allowed: boolean | null;
  legacy_source: string;
  legacy_reason: string;
  catalog_allowed: boolean | null;
  catalog_source: string;
  catalog_reason: string;
  comparison: AuditComparison;
  status: 'permitido' | 'denegado' | 'no_concluyente';
  scope: string;
  context: { branch_id: number | null; document_id: number | null };
  diagnostic_only: true;
}

export interface VisualAuditResponse {
  mode: string;
  note: string;
  view: AuditPerspective;
  rows: VisualAuditRow[];
  summary: {
    total: number;
    limit: number;
    offset: number;
    evaluated: number;
    allowed: number;
    denied: number;
    unknown: number;
    differences: number;
    matches: number;
  };
  coverage: { catalog_partial: boolean; message: string };
}

export interface VisualAuditFilters {
  view: AuditPerspective;
  user_id?: number;
  module_key?: string;
  action_key?: string;
  branch_id?: number;
  document_id?: number;
  role?: string;
  q?: string;
  limit: number;
  offset: number;
}

@Injectable({ providedIn: 'root' })
export class PermissionVisualAuditService {
  private readonly apiUrl = `${environment.apiUrl}/permissions/catalog/audit/matrix`;

  constructor(private readonly http: HttpClient) {}

  getMatrix(filters: VisualAuditFilters): Observable<VisualAuditResponse> {
    let params = new HttpParams();
    Object.entries(filters).forEach(([key, value]) => {
      if (value !== null && value !== undefined && value !== '') {
        params = params.set(key, String(value));
      }
    });
    return this.http.get<VisualAuditResponse>(this.apiUrl, { params });
  }
}
