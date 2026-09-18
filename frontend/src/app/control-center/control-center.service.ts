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
  MarketingSalesFunnelResponse,
} from '../marketing-sales-funnel/marketing-sales-funnel.models';
import {
  MarketingSalesFunnelService,
} from '../marketing-sales-funnel/marketing-sales-funnel.service';
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

export type ControlOperationalForecastMetricKey =
  | 'ingreso'
  | 'clientes_nuevos'
  | 'reactivaciones'
  | 'bajas'
  | 'tienda';

export interface ControlOperationalForecastMetric {
  metric_key: ControlOperationalForecastMetricKey;
  actual_mtd: string | null;
  projected_close: string | null;
  benchmark: string | null;
  benchmark_kind: 'target' | 'limit';
  projected_gap: string | null;
  status: 'available' | 'insufficient_history';
  method: string;
  branch_methods: string[];
  coverage: {
    total_branches: number;
    actual_available_branches: number;
    benchmark_available_branches: number;
    projected_available_branches: number;
    unavailable_branches_count: number;
  };
  projected_excess?: string | null;
  projected_remaining_margin?: string | null;
  projected_limit_usage_pct?: string | null;
  projected_compliance_pct?: string | null;
}

export interface ControlOperationalForecastBranchMetric {
  metric_key: ControlOperationalForecastMetricKey;
  actual_mtd: string | null;
  projected_close: string | null;
  benchmark: string | null;
  benchmark_kind: 'target' | 'limit';
  projected_gap: string | null;
  status: 'available' | 'insufficient_history';
  method: string | null;
  projection?: {
    status?: string;
    method?: string;
    projected_close?: string | null;
    recent_daily_average?: string | null;
    remaining_days?: number;
    historical_progress_pct?: string | null;
    historical_samples_count?: number;
  };
}

export interface ControlOperationalForecastResponse {
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
    status: 'available' | 'partial';
    total_branches: number;
    metrics: Record<
      ControlOperationalForecastMetricKey,
      ControlOperationalForecastMetric
    >;
  };
  branches: Array<{
    sucursal_id: number;
    sucursal_canon: string;
    sucursal: string;
    region_key: string;
    region_label: string;
    metrics: Record<
      ControlOperationalForecastMetricKey,
      ControlOperationalForecastBranchMetric
    >;
  }>;
}

@Injectable({ providedIn: 'root' })
export class ControlCenterService {
  private readonly http = inject(HttpClient);
  private readonly trackService = inject(TrackService);
  private readonly marketingSalesFunnelService = inject(MarketingSalesFunnelService);
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

  getOperationalForecast(
    request: ControlContextRequest,
    generationMode = 'manual_preview',
  ): Observable<ControlOperationalForecastResponse> {
    const params = this.buildScopeParams(request).set(
      'generation_mode',
      generationMode,
    );

    return this.http.get<ControlOperationalForecastResponse>(
      `${this.baseUrl}/operational-forecast`,
      { params },
    );
  }

  getForecastCatalogs(): Observable<TrackForecastCenterCatalogsResponse> {
    return this.trackService.getForecastCenterCatalogs();
  }

  getForecast(params: TrackForecastCenterParams): Observable<TrackForecastCenterResponse> {
    return this.trackService.getForecastCenter(params);
  }

  getMarketing(
    month: string,
    cutoffDate: string,
  ): Observable<MarketingSalesFunnelResponse> {
    return this.marketingSalesFunnelService.getDashboard(
      month,
      [],
      cutoffDate,
      'latest_available_at_or_before',
    );
  }

  getMaintenance(startDate: string, endDate: string): Observable<MaintenancePlannerBoard> {
    return this.maintenancePlannerService.getBoard({
      startDate,
      endDate,
      estado: 'todos',
      audience: 'analytical',
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
