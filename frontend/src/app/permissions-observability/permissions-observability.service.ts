// frontend/src/app/permissions-observability/permissions-observability.service.ts

import { HttpClient, HttpParams } from '@angular/common/http';
import { Injectable } from '@angular/core';
import { Observable } from 'rxjs';

import { environment } from 'src/environments/environment';


export interface PermissionUserOption {
  id: number;
  username: string;
  email?: string | null;
  rol: string;
  department_id?: number | null;
  sucursal_id?: number | null;
  sucursales_ids: number[];
}

export interface PermissionModule {
  id: number;
  key: string;
  name: string;
  description?: string | null;
  is_active: boolean;
  actions_count: number;
}

export interface PermissionAction {
  id: number;
  module_id: number;
  module_key?: string | null;
  key: string;
  full_key: string;
  name: string;
  description?: string | null;
  risk_level: string;
  is_active: boolean;
}

export interface PermissionRouteMap {
  id: number;
  method: string;
  route: string;
  endpoint_function: string;
  source_file: string;
  module_id?: number | null;
  module_key?: string | null;
  action_id?: number | null;
  action_full_key?: string | null;
  current_guard?: string | null;
  current_scope?: string | null;
  review_status: string;
  notes?: string | null;
  is_active: boolean;
}

export interface EffectivePermissionAction extends PermissionAction {
  allowed: boolean;
  source: string;
  reason: string;
  scope_type: string;
  scope_values: unknown[];
  details?: Record<string, unknown>;
}

export interface EffectivePermissionResponse {
  status: string;
  mode: string;
  authorization_source: string;
  note: string;
  user: {
    id: number;
    username: string;
    email?: string | null;
    role: string;
    department_id?: number | null;
    primary_sucursal_id?: number | null;
    sucursales: Array<{
      sucursal_id: number;
      name?: string | null;
      operational_status?: string | null;
      is_primary: boolean;
    }>;
  };
  summary: {
    actions_total: number;
    allowed_count: number;
    denied_count: number;
  };
  operator_context: {
    warehouse: Record<string, boolean>;
    planning: Record<string, boolean>;
  };
  actions: EffectivePermissionAction[];
}


export interface PermissionGrantRelatedUser {
  id: number;
  username: string;
  email?: string | null;
  rol: string;
}

export interface PermissionGrant {
  id: number;
  principal_type: string;
  principal_user_id?: number | null;
  principal_user?: PermissionGrantRelatedUser | null;
  principal_role_key?: string | null;
  module_id?: number | null;
  module_key?: string | null;
  module_name?: string | null;
  action_id?: number | null;
  action_full_key?: string | null;
  action_name?: string | null;
  action_risk_level?: string | null;
  effect: string;
  scope_type: string;
  scope_branch_id?: number | null;
  scope_branch_ids: number[];
  scope_department_id?: number | null;
  scope_payload: Record<string, unknown>;
  reason: string;
  is_active: boolean;
  starts_at?: string | null;
  expires_at?: string | null;
  created_by_user_id?: number | null;
  created_by_user?: PermissionGrantRelatedUser | null;
  updated_by_user_id?: number | null;
  updated_by_user?: PermissionGrantRelatedUser | null;
  created_at?: string | null;
  updated_at?: string | null;
  deleted_at?: string | null;
}

export interface PermissionGrantAuditLog {
  id: number;
  grant_id?: number | null;
  event_type: string;
  before_payload: Record<string, unknown>;
  after_payload: Record<string, unknown>;
  changed_by_user_id?: number | null;
  changed_by_user?: PermissionGrantRelatedUser | null;
  reason?: string | null;
  request_ip?: string | null;
  user_agent?: string | null;
  created_at?: string | null;
}

export interface PermissionGrantsResponse {
  status: string;
  mode: string;
  note: string;
  summary: {
    total: number;
    limit: number;
    offset: number;
  };
  grants: PermissionGrant[];
}

export interface PermissionGrantAuditResponse {
  status: string;
  mode: string;
  grant: PermissionGrant;
  summary: {
    total: number;
    limit: number;
    offset: number;
  };
  audit_logs: PermissionGrantAuditLog[];
}

export interface PermissionGrantFilters {
  active?: 'true' | 'false' | 'all';
  principal_type?: string;
  principal_user_id?: number | null;
  principal_role_key?: string;
  module_id?: number | null;
  module_key?: string;
  action_id?: number | null;
  action_full_key?: string;
  effect?: string;
  scope_type?: string;
  limit?: number;
  offset?: number;
}

export interface PermissionGrantAuditFilters {
  event_type?: string;
  limit?: number;
  offset?: number;
}

@Injectable({
  providedIn: 'root',
})
export class PermissionsObservabilityService {
  private readonly apiUrl = `${environment.apiUrl}/permissions/catalog`;

  constructor(private readonly http: HttpClient) {}


  searchUsers(q: string = '', limit: number = 25): Observable<{ users: PermissionUserOption[] }> {
    let params = new HttpParams().set('limit', String(limit));

    if (q.trim()) {
      params = params.set('q', q.trim());
    }

    return this.http.get<{ users: PermissionUserOption[] }>(
      `${this.apiUrl}/users/search`,
      { params },
    );
  }

  getModules(active: 'true' | 'false' | 'all' = 'true'): Observable<{ modules: PermissionModule[] }> {
    const params = new HttpParams().set('active', active);
    return this.http.get<{ modules: PermissionModule[] }>(`${this.apiUrl}/modules`, { params });
  }

  getActions(filters?: {
    active?: 'true' | 'false' | 'all';
    module?: string;
    risk_level?: string;
  }): Observable<{ actions: PermissionAction[] }> {
    let params = new HttpParams().set('active', filters?.active || 'true');

    if (filters?.module) {
      params = params.set('module', filters.module);
    }

    if (filters?.risk_level) {
      params = params.set('risk_level', filters.risk_level);
    }

    return this.http.get<{ actions: PermissionAction[] }>(`${this.apiUrl}/actions`, { params });
  }

  getRoutes(filters?: {
    active?: 'true' | 'false' | 'all';
    module?: string;
    review_status?: string;
  }): Observable<{ routes: PermissionRouteMap[] }> {
    let params = new HttpParams().set('active', filters?.active || 'true');

    if (filters?.module) {
      params = params.set('module', filters.module);
    }

    if (filters?.review_status) {
      params = params.set('review_status', filters.review_status);
    }

    return this.http.get<{ routes: PermissionRouteMap[] }>(`${this.apiUrl}/routes`, { params });
  }

  getEffectivePermissions(
    userId: number,
    active: 'true' | 'false' | 'all' = 'true',
  ): Observable<EffectivePermissionResponse> {
    const params = new HttpParams().set('active', active);
    return this.http.get<EffectivePermissionResponse>(
      `${this.apiUrl}/users/${userId}/effective`,
      { params },
    );
  }

  getGrants(filters?: PermissionGrantFilters): Observable<PermissionGrantsResponse> {
    let params = new HttpParams()
      .set('active', filters?.active || 'true')
      .set('limit', String(filters?.limit ?? 50))
      .set('offset', String(filters?.offset ?? 0));

    if (filters?.principal_type) {
      params = params.set('principal_type', filters.principal_type);
    }

    if (filters?.principal_user_id) {
      params = params.set('principal_user_id', String(filters.principal_user_id));
    }

    if (filters?.principal_role_key) {
      params = params.set('principal_role_key', filters.principal_role_key);
    }

    if (filters?.module_id) {
      params = params.set('module_id', String(filters.module_id));
    }

    if (filters?.module_key) {
      params = params.set('module_key', filters.module_key);
    }

    if (filters?.action_id) {
      params = params.set('action_id', String(filters.action_id));
    }

    if (filters?.action_full_key) {
      params = params.set('action_full_key', filters.action_full_key);
    }

    if (filters?.effect) {
      params = params.set('effect', filters.effect);
    }

    if (filters?.scope_type) {
      params = params.set('scope_type', filters.scope_type);
    }

    return this.http.get<PermissionGrantsResponse>(`${this.apiUrl}/grants`, { params });
  }

  getGrantAudit(
    grantId: number,
    filters?: PermissionGrantAuditFilters,
  ): Observable<PermissionGrantAuditResponse> {
    let params = new HttpParams()
      .set('limit', String(filters?.limit ?? 50))
      .set('offset', String(filters?.offset ?? 0));

    if (filters?.event_type) {
      params = params.set('event_type', filters.event_type);
    }

    return this.http.get<PermissionGrantAuditResponse>(
      `${this.apiUrl}/grants/${grantId}/audit`,
      { params },
    );
  }
}


