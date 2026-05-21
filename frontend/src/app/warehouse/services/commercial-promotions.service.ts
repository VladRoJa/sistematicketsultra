// frontend\src\app\warehouse\services\commercial-promotions.service.ts


import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';

import { environment } from '../../../environments/environment';

export interface CommercialPromotionsMetadata {
  source: string;
  scope: string;
  excludes?: string[];
  classification_source?: string;
  canonicality_rule?: string;
  impact_rule?: {
    impacto_fuerte: string;
    impacto_medio: string;
    impacto_bajo_no_concluyente: string;
  };
  purpose?: string;
  candidate_patterns?: string[];
}

export interface CommercialPromotionsSummary {
  period: {
    first_month: string | null;
    last_month: string | null;
    last_snapshot_cutoff: string | null;
    analyzed_months: number;
  };
  winner: CommercialPromotionsRankingItem | null;
  totals: {
    denominador_venta_total_canonizado: number | null;
    ingreso_promo_total: number;
    porcentaje_promo_total: number | null;
  };
  impact: {
    strong_branches: number;
    medium_branches: number;
    low_branches: number;
    total_branches: number;
  };
  unmapped: {
    candidate_count: number;
  };
}

export interface CommercialPromotionsSummaryResponse {
  summary: CommercialPromotionsSummary;
  metadata: CommercialPromotionsMetadata;
}

export interface CommercialPromotionsRankingItem {
  commercial_canon: string;
  family: string;
  meses_con_venta: number;
  operaciones: number;
  unidades: number;
  ingreso_promo: number;
  ticket_promedio: number;
  denominador_venta_total_canonizado: number;
  porcentaje_sobre_venta_total: number;
  requiere_validacion_negocio: boolean;
}

export interface CommercialPromotionsRankingResponse {
  items: CommercialPromotionsRankingItem[];
  metadata: CommercialPromotionsMetadata;
}

export interface CommercialPromotionsByMonthItem {
  mes: string;
  corte_snapshot: string;
  ranking_mes: number;
  commercial_canon: string;
  family: string;
  operaciones: number;
  unidades: number;
  ingreso_promo: number;
  ticket_promedio: number;
  denominador_venta_total_mes: number;
  porcentaje_sobre_venta_total_mes: number;
  requiere_validacion_negocio: boolean;
}

export interface CommercialPromotionsByMonthResponse {
  items: CommercialPromotionsByMonthItem[];
  metadata: CommercialPromotionsMetadata;
}

export interface CommercialPromotionsByBranchItem {
  sucursal_canon: string;
  promo_ganadora: string;
  family: string;
  meses_con_venta: number;
  operaciones: number;
  unidades: number;
  ingreso_promo: number;
  ticket_promedio: number;
  denominador_venta_total_sucursal: number;
  porcentaje_sobre_venta_total_sucursal: number;
  lectura_impacto: 'impacto_fuerte' | 'impacto_medio' | 'impacto_bajo_no_concluyente';
  requiere_validacion_negocio: boolean;
}

export interface CommercialPromotionsByBranchResponse {
  items: CommercialPromotionsByBranchItem[];
  metadata: CommercialPromotionsMetadata;
}

export interface CommercialPromotionsUnmappedItem {
  descripcion_raw: string;
  operaciones: number;
  unidades: number;
  ingreso_total: number;
  ticket_promedio: number;
  sucursales_detectadas: number;
  primer_mes_detectado: string;
  ultimo_mes_detectado: string;
}

export interface CommercialPromotionsUnmappedResponse {
  items: CommercialPromotionsUnmappedItem[];
  metadata: CommercialPromotionsMetadata;
}

@Injectable({
  providedIn: 'root',
})
export class CommercialPromotionsService {
  private readonly baseUrl = `${environment.apiUrl}/warehouse/commercial/promotions`;

  constructor(private readonly http: HttpClient) {}

  getSummary(): Observable<CommercialPromotionsSummaryResponse> {
    return this.http.get<CommercialPromotionsSummaryResponse>(`${this.baseUrl}/summary`);
  }

  getRanking(): Observable<CommercialPromotionsRankingResponse> {
    return this.http.get<CommercialPromotionsRankingResponse>(`${this.baseUrl}/ranking`);
  }

  getByMonth(): Observable<CommercialPromotionsByMonthResponse> {
    return this.http.get<CommercialPromotionsByMonthResponse>(`${this.baseUrl}/by-month`);
  }

  getByBranch(): Observable<CommercialPromotionsByBranchResponse> {
    return this.http.get<CommercialPromotionsByBranchResponse>(`${this.baseUrl}/by-branch`);
  }

  getUnmapped(): Observable<CommercialPromotionsUnmappedResponse> {
    return this.http.get<CommercialPromotionsUnmappedResponse>(`${this.baseUrl}/unmapped`);
  }
}