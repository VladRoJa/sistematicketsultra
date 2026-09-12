import { HttpClient, HttpParams } from '@angular/common/http';
import { Injectable } from '@angular/core';
import { Observable } from 'rxjs';

import { environment } from 'src/environments/environment';

import { MarketingSalesFunnelResponse } from './marketing-sales-funnel.models';


@Injectable({
  providedIn: 'root',
})
export class MarketingSalesFunnelService {
  private readonly apiUrl = `${environment.apiUrl}/marketing`;

  constructor(private readonly http: HttpClient) {}

  getDashboard(month: string): Observable<MarketingSalesFunnelResponse> {
    const params = new HttpParams().set('month', month);

    return this.http.get<MarketingSalesFunnelResponse>(
      `${this.apiUrl}/sales-funnel`,
      { params },
    );
  }
}
