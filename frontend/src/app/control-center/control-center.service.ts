import { HttpClient, HttpParams } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import { environment } from 'src/environments/environment';
import {
  TrackForecastCenterCatalogsResponse,
  TrackForecastCenterParams,
  TrackForecastCenterResponse,
  TrackService,
} from '../services/track.service';
import {
  MarketingDashboardResponse,
} from '../marketing-conversion/marketing.models';
import { MarketingService } from '../marketing-conversion/marketing.service';
import {
  MaintenancePlannerBoard,
  MaintenancePlannerService,
} from '../maintenance-planner/maintenance-planner.service';

export type ControlScopeType = 'GLOBAL' | 'REGION' | 'BRANCH_POOL' | 'BRANCH';

export interface ControlScope {
  type: ControlScopeType;
  region_keys: string[];
  branch_ids: number[];
}

export interface ControlContextResponse {
  status: 'ok';
  contract_version: string;
  cutoff_date: string;
  access: {
    role: string;
    max_scope: ControlScopeType;
    authorized_scope: ControlScope;
    allowed_domains: string[];
    navigable_dimensions: string[];
  };
  effective_scope: ControlScope;
}

export interface ControlContextRequest {
  cutoffDate?: string;
  scopeType?: ControlScopeType;
  regionKey?: string | null;
  branchId?: number | null;
}

export interface ControlRetentionBranch {
  sucursal_id: number | null;
  sucursal_canon: string;
  sucursal: string;
  bajas_reales_mtd: number | null;
  meta_bajas_mes: number | null;
  limit_usage_ratio: number | null;
  remaining_margin: number | null;
}

export interface ControlRetentionResponse {
  status: 'ok';
  contract_version: string;
  cutoff_date: string;
  generation_mode: string;
  effective_scope: ControlScope;
  resolved_version: {
    id: number;
    version_type: string;
    status: string;
  } | null;
  summary: {
    bajas_reales_mtd: number | null;
    meta_bajas_mes: number | null;
    limit_usage_ratio: number | null;
    remaining_margin: number | null;
    branch_count: number;
    actual_coverage_branch_count: number;
    target_coverage_branch_count: number;
  };
  branches: ControlRetentionBranch[];
}

@Injectable({ providedIn: 'root' })
export class ControlCenterService {
  private readonly http = inject(HttpClient);
  private readonly trackService = inject(TrackService);
  private readonly marketingService = inject(MarketingService);
  private readonly maintenancePlannerService = inject(MaintenancePlannerService);
  private readonly baseUrl = `${environment.apiUrl}/control`;

  getContext(request: ControlContextRequest = {}): Observable<ControlContextResponse> {
    return this.http.get<ControlContextResponse>(`${this.baseUrl}/context`, {
      params: this.buildScopeParams(request),
    });
  }

  getRetention(
    request: ControlContextRequest,
    generationMode = 'manual_preview',
  ): Observable<ControlRetentionResponse> {
    const params = this.buildScopeParams(request).set(
      'generation_mode',
      generationMode,
    );
    return this.http.get<ControlRetentionResponse>(`${this.baseUrl}/retention`, {
      params,
    });
  }

  getForecastCatalogs(): Observable<TrackForecastCenterCatalogsResponse> {
    return this.trackService.getForecastCenterCatalogs();
  }

  getForecast(params: TrackForecastCenterParams): Observable<TrackForecastCenterResponse> {
    return this.trackService.getForecastCenter(params);
  }

  getMarketing(month: string): Observable<MarketingDashboardResponse> {
    return this.marketingService.getDashboard(month);
  }

  getMaintenance(startDate: string, endDate: string): Observable<MaintenancePlannerBoard> {
    return this.maintenancePlannerService.getBoard({
      startDate,
      endDate,
      estado: 'todos',
    });
  }

  private buildScopeParams(request: ControlContextRequest): HttpParams {
    let params = new HttpParams();

    if (request.cutoffDate) {
      params = params.set('cutoff_date', request.cutoffDate);
    }
    if (request.scopeType) {
      params = params.set('scope_type', request.scopeType);
    }
    if (request.regionKey) {
      params = params.set('region_key', request.regionKey);
    }
    if (request.branchId) {
      params = params.set('branch_id', String(request.branchId));
    }

    return params;
  }
}
