import { Injectable } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { Observable } from 'rxjs';
import { environment } from '../../environments/environment';
import { Job, Run, RunsResponse, Summary, Dataset, TimelineResponse, AutomationDiagnostic, WorkerHealthResponse, EffectiveSchedulesResponse } from './automation-control.models';
@Injectable({ providedIn:'root' })
export class AutomationControlService {
  private readonly url = `${environment.apiUrl}/automation-control`;
  constructor(private readonly http: HttpClient) {}
  summary():Observable<Summary> { return this.http.get<Summary>(`${this.url}/summary`); }
  workerHealth():Observable<WorkerHealthResponse> { return this.http.get<WorkerHealthResponse>(`${this.url}/workers/health`); }
  effectiveSchedules():Observable<EffectiveSchedulesResponse> {
    return this.http.get<EffectiveSchedulesResponse>(`${this.url}/jobs/effective-schedules`);
  }
  jobs():Observable<{jobs:Job[]}> { return this.http.get<{jobs:Job[]}>(`${this.url}/jobs`); }
  datasets():Observable<{datasets:Dataset[]}> { return this.http.get<{datasets:Dataset[]}>(`${this.url}/datasets`); }
  timeline(day:string):Observable<TimelineResponse> {
    return this.http.get<TimelineResponse>(`${this.url}/timeline`, {params:new HttpParams().set('date',day)});
  }
  diagnostic(jobKey:string,runId:number):Observable<{diagnostic:AutomationDiagnostic}> {
    return this.http.get<{diagnostic:AutomationDiagnostic}>(
      `${this.url}/jobs/${encodeURIComponent(jobKey)}/runs/${runId}/diagnostic`);
  }
  lastError(jobKey:string,businessDate?:string):Observable<{diagnostic:AutomationDiagnostic}> {
    const params=businessDate?new HttpParams().set('business_date',businessDate):new HttpParams();
    return this.http.get<{diagnostic:AutomationDiagnostic}>(
      `${this.url}/jobs/${encodeURIComponent(jobKey)}/last-error`,{params});
  }
  runs(jobKey:string,offset:number,limit:number):Observable<RunsResponse> {
    const params = new HttpParams().set('offset',String(offset)).set('limit',String(limit));
    return this.http.get<RunsResponse>(`${this.url}/jobs/${encodeURIComponent(jobKey)}/runs`,{params});
  }
}
