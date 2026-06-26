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
}
