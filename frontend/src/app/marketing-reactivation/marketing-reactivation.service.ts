import { HttpClient, HttpParams } from '@angular/common/http';
import { Injectable } from '@angular/core';
import { Observable } from 'rxjs';

import { environment } from 'src/environments/environment';

import {
  ReactivationCandidatesResponse,
  ReactivationSourcesResponse,
} from './marketing-reactivation.models';

@Injectable({
  providedIn: 'root',
})
export class MarketingReactivationService {
  private readonly apiUrl = `${environment.apiUrl}/marketing/reactivation`;

  constructor(private readonly http: HttpClient) {}

  getSources(): Observable<ReactivationSourcesResponse> {
    return this.http.get<ReactivationSourcesResponse>(
      `${this.apiUrl}/sources`,
    );
  }

  getCandidates(
    vencidosSnapshotId: number,
    iventasPeriodKey: string,
  ): Observable<ReactivationCandidatesResponse> {
    const params = new HttpParams()
      .set('vencidos_snapshot_id', String(vencidosSnapshotId))
      .set('iventas_period_key', iventasPeriodKey);

    return this.http.get<ReactivationCandidatesResponse>(
      `${this.apiUrl}/candidates`,
      { params },
    );
  }
}
