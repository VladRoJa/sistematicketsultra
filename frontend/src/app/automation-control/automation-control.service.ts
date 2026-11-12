import { Injectable } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { Observable } from 'rxjs';
import { environment } from '../../environments/environment';
import { Job, Run, RunsResponse, Summary, Dataset, TimelineResponse, AutomationDiagnostic, WorkerHealthResponse, EffectiveSchedulesResponse, GascaSmsQueueTelemetry, GascaSmsPulseTelemetry, SchedulerAlertSummary } from './automation-control.models';
@Injectable({ providedIn:'root' })
export class AutomationControlService {
  private readonly url = `${environment.apiUrl}/automation-control`;
  constructor(private readonly http: HttpClient) {}
  cobranzaPilotEvent(): Observable<{status:string; event: CobranzaPilotEvent | null}> {
    return this.http.get<{status:string; event:CobranzaPilotEvent | null}>(
      `${this.url}/cobranza/pilot-event`);
  }
  alertSummary():Observable<SchedulerAlertSummary> {
    return this.http.get<SchedulerAlertSummary>(`${this.url}/alerts/summary`);
  }
  summary():Observable<Summary> { return this.http.get<Summary>(`${this.url}/summary`); }
  smsPulse():Observable<GascaSmsPulseTelemetry> {
    return this.http.get<GascaSmsPulseTelemetry>(`${this.url}/sms-gasca/pulse`);
  }
  smsQueue():Observable<GascaSmsQueueTelemetry> {
    return this.http.get<GascaSmsQueueTelemetry>(`${this.url}/sms-gasca/queue`);
  }
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

export interface CobranzaPilotEvent {
  event_id: string;
  campaign_id: number;
  business_date: string;
  branch: string;
  recipient_count: number;
  accepted_count: number;
  stage: 'PREPARED' | 'QUEUED' | 'RUNNING' | 'COMPLETED' | 'REVIEW_REQUIRED' | 'STOPPED' | 'STOP_REQUESTED' | 'AUTO_SEND_BLOCKED';
  has_job: boolean;
}
