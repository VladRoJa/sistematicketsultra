// frontend/src/app/warehouse/services/warehouse-catalogs.service.ts


import { Injectable, inject } from '@angular/core';
import { HttpClient, HttpHeaders } from '@angular/common/http';
import { Observable } from 'rxjs';
import { environment } from 'src/environments/environment';

export interface WarehouseCatalogOption {
  id: number;
  key: string;
  label: string;
}

export interface WarehouseReportTypeCatalogOption extends WarehouseCatalogOption {
  family_id: number;
  default_source_id: number | null;
  default_operational_role_id: number | null;
  default_period_type: string | null;
}

export interface WarehouseCatalogsResponse {
  sources: WarehouseCatalogOption[];
  families: WarehouseCatalogOption[];
  operational_roles: WarehouseCatalogOption[];
  report_types: WarehouseReportTypeCatalogOption[];
}

@Injectable({
  providedIn: 'root'
})
export class WarehouseCatalogsService {
  private readonly http = inject(HttpClient);
  private readonly apiUrl = `${environment.apiUrl}/warehouse/catalogs`;

  getCatalogs(): Observable<WarehouseCatalogsResponse> {
    return this.http.get<WarehouseCatalogsResponse>(this.apiUrl, {
      headers: this.buildAuthHeaders(),
    });
  }

  private buildAuthHeaders(): HttpHeaders {
    const token = localStorage.getItem('token') || '';

    return new HttpHeaders({
      Authorization: `Bearer ${token}`,
    });
  }
}