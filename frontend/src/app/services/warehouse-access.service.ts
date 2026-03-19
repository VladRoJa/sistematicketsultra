// frontend\src\app\services\warehouse-access.service.ts

import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';
import { environment } from 'src/environments/environment';

export interface WarehouseAccessResponse {
  allowed: boolean;
  module: string;
}

@Injectable({
  providedIn: 'root'
})
export class WarehouseAccessService {
  private readonly apiUrl = `${environment.apiUrl}/warehouse`;

  constructor(private http: HttpClient) {}

  checkAccess(): Observable<WarehouseAccessResponse> {
    return this.http.get<WarehouseAccessResponse>(`${this.apiUrl}/access`);
  }
}