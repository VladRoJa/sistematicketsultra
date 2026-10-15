import { CommonModule } from '@angular/common';
import { Component, OnDestroy, OnInit } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatDialog, MatDialogModule } from '@angular/material/dialog';
import { MatIconModule } from '@angular/material/icon';
import { AutomationObservationDialogComponent, AutomationObservationDialogData } from './automation-observation-dialog.component';
import { AutomationErrorDetailDialogComponent, AutomationErrorDialogData } from './automation-error-detail-dialog.component';
import { catchError, forkJoin, from, map, mergeMap, of, Subject, takeUntil } from 'rxjs';
import { AutomationControlService } from './automation-control.service';
import { DataFreshnessService, DatasetFreshness, FreshnessDatasetKey } from '../shared/data-freshness-indicator/data-freshness.service';
import { DataFreshnessIndicatorComponent } from '../shared/data-freshness-indicator/data-freshness-indicator.component';
import { classifyObservationRuns, classifyReferenceHour, currentTijuanaClock, ObservationState, ReferenceState } from './automation-control-timeline-display';
import { Job, Run, Summary, Dataset, TimelineWorker, TimelineJob, TimelineObservation, WorkerHealth, WorkerLiveness, EffectiveJobSchedule } from './automation-control.models';

@Component({ selector:'app-automation-control',standalone:true,imports:[CommonModule,FormsModule,MatDialogModule,MatIconModule,DataFreshnessIndicatorComponent],
  templateUrl:'./automation-control.component.html',styleUrls:['./automation-control.component.css'] })
export class AutomationControlComponent implements OnInit,OnDestroy {
  readonly pageSize=20;
  readonly hours=Array.from({length:24},(_,i)=>String(i).padStart(2,'0')+':00');
  tijuanaClock=currentTijuanaClock(new Date());
  timelineDate=new Date().toLocaleDateString('en-CA',{timeZone:'America/Tijuana'});
  timelineWorkers:TimelineWorker[]=[];
  workerHealth:WorkerHealth[]=[];
  effectiveSchedules:EffectiveJobSchedule[]=[];
  configUnavailable=false;
  healthUnavailable=false;
  healthCheckedAt:string|null=null;
  loadingTimeline=false;
  timelineError='';
  selectedObservation:TimelineObservation|null=null;
  selectedObservationJob='';

  private readonly destroyed$=new Subject<void>();
  private sequence=0;
  private latestRunSequence=0;
  latestRuns:Record<string,Run|null>={};
  latestRunUnavailable:Record<string,boolean>={};
  summary:Summary|null=null; jobs:Job[]=[]; datasets:Dataset[]=[];
  datasetEvidence:Record<string,DatasetFreshness|null>={};
  selected:Job|null=null; runs:Run[]=[]; coverage='UNKNOWN'; offset=0; hasMore=false;
  domain=''; search=''; loading=true; loadingRuns=false; error=''; runsError='';
  constructor(private readonly api:AutomationControlService,
    private readonly freshnessApi:DataFreshnessService, private readonly dialog:MatDialog){}
  ngOnInit():void { this.refresh(); }
  ngOnDestroy():void { this.destroyed$.next();this.destroyed$.complete(); }
  get domains():string[] {return [...new Set(this.jobs.map(j=>j.domain))].sort();}
  get visibleJobs():Job[] {
    const text=this.search.trim().toLowerCase();
    return this.jobs.filter(j=>(!this.domain||j.domain===this.domain)&&
      (!text||[j.label,j.key,j.worker_key].some(v=>v.toLowerCase().includes(text))));
  }
  get page():number {return Math.floor(this.offset/this.pageSize)+1;}
  isFreshnessDataset(key:string):boolean {
    return key==='marketing.sales_funnel'||key==='track.daily';
  }
  freshnessModuleKey(key:string):FreshnessDatasetKey {
    // Template guards unknown future datasets; no implicit third SLA is assumed.
    return key==='track.daily' ? 'track.daily' : 'marketing.sales_funnel';
  }
  datasetEvidenceLabel(datasetKey:string):string {
    const state=this.datasetEvidence[datasetKey];
    if(!state)return 'Frescura no verificable';
    if(datasetKey==='track.daily'){
      if(state.status==='LATE')return 'Base nocturna atrasada';
      if(state.status==='LAGGING')return 'Base nocturna pendiente';
      if(state.status==='NOT_DUE')return 'Base nocturna: aún no vence';
    }
    if(state.latest_complete_business_date)
      return 'Corte conjunto: '+state.latest_complete_business_date;
    if(state.latest_catalog_matched_business_date)
      return 'Coincide con catálogo actual: '+state.latest_catalog_matched_business_date;
    if(state.latest_observed_business_date)
      return 'Evidencia: '+state.latest_observed_business_date;
    return 'Sin corte certificado';
  }
  datasetEvidenceDetail(datasetKey:string):string {
    const evidence=this.datasetEvidence[datasetKey];
    if(!evidence)return 'No se pudo consultar evidencia de cortes.';
    const coverage=evidence.track_coverage?.coverage;
    if(!coverage)return evidence.detail;
    const deadline=evidence.track_base_sla?.due_at;
    const slaText=deadline?' Límite base nocturna: '+deadline+'.':'';
    return evidence.detail+slaText+' Filas Track: '+coverage.actual_branch_count+
      '/'+coverage.expected_branch_count+' sucursales; faltantes: '+
      coverage.missing_branch_codes.length+', sobrantes: '+
      coverage.unexpected_branch_codes.length+'.';
  }
  effectiveJob(jobKey:string):EffectiveJobSchedule|undefined {
    return this.effectiveSchedules.find(j=>j.job_key===jobKey);
  }
  effectiveLabel(jobKey:string):string {
    const entry=this.effectiveJob(jobKey);
    if(!entry||entry.state==='UNVERIFIED'||!entry.schedule)return 'Sin verificar';
    if(entry.state==='DISABLED')return 'Deshabilitado';
    const schedule=entry.schedule;
    if(schedule.kind==='HOURLY_WINDOW'&&schedule.slots.length>1){
      return schedule.slots[0]+'–'+schedule.slots[schedule.slots.length-1]+' (horario local)';
    }
    if(schedule.slots.length) return schedule.slots.join(', ');
    if(schedule.interval_seconds){
      const n=schedule.interval_seconds;
      return n%60===0?'Cada '+(n/60)+' min':'Cada '+n+' s';
    }
    const names:Record<string,string>={
      CONDITIONAL:'Según condiciones',PENDING_REQUEST:'Cuando hay solicitud',
      NIGHTLY_WINDOW:'Ventana nocturna condicionada',
      INTERVAL_CHECK:'Comprobación periódica',
    };
    return names[schedule.kind]||'Condicional';
  }
  effectiveDetail(jobKey:string):string {
    const entry=this.effectiveJob(jobKey);
    if(!entry||!entry.schedule||entry.state==='UNVERIFIED') {
      return 'El worker no ha confirmado una programación vigente.';
    }
    const part='Configuración reportada por el worker en '+entry.schedule.timezone+'.';
    return part+(entry.schedule.conditional?
      ' Su ejecución depende de prioridades, reintentos o disponibilidad; no es una garantía.':
      ' Horario nominal, no confirma que la ejecución vaya a terminar correctamente.');
  }
  get healthyWorkers():number {
    return this.workerHealth.filter(worker=>worker.status==='HEALTHY').length;
  }
  workerState(workerKey:string):WorkerHealth|undefined {
    return this.workerHealth.find(worker=>worker.worker_key===workerKey);
  }
  workerHealthLabel(workerKey:string):string {
    const status=this.workerState(workerKey)?.status??'UNKNOWN';
    const names:Record<WorkerLiveness,string>={
      HEALTHY:'Latido vigente',DEGRADED:'Revisar',UNREACHABLE:'Sin latido',
      DISABLED:'Deshabilitado',UNKNOWN:'Desconocido',
    };
    return names[status];
  }
  workerHealthIcon(workerKey:string):string {
    const status=this.workerState(workerKey)?.status??'UNKNOWN';
    const icons:Record<WorkerLiveness,string>={
      HEALTHY:'favorite',DEGRADED:'warning_amber',UNREACHABLE:'heart_broken',
      DISABLED:'pause_circle',UNKNOWN:'help_outline',
    };
    return icons[status];
  }
  workerHealthClass(workerKey:string):string {
    return 'health-'+(this.workerState(workerKey)?.status??'UNKNOWN').toLowerCase();
  }
  workerHealthDetail(workerKey:string):string {
    const worker=this.workerState(workerKey);
    if(!worker||!worker.last_seen_at_utc) return 'Sin evidencia de latido persistido';
    const reason:Record<string,string>={
      RECENT_HEARTBEAT:'Último latido dentro de la tolerancia',
      MULTIPLE_ACTIVE_INSTANCES:'Varias instancias activas; revisar duplicidad',
      WORKER_DISABLED:'Worker deshabilitado',
      HEARTBEAT_LATE:'Último latido fuera de la tolerancia',
      HEARTBEAT_EXPIRED:'Sin latidos recientes; estado del proceso no confirmado',
      CLOCK_SKEW:'Hora del worker fuera de sincronía',
    };
    return (reason[worker.reason_code]??'Estado sin verificar')+
      ' · Último latido: '+this.formatDate(worker.last_seen_at_utc);
  }
  refresh():void {
    this.loadTimeline();
    this.sequence++;this.latestRunSequence++;this.loading=true;this.error='';
    forkJoin({summary:this.api.summary(),jobs:this.api.jobs(),datasets:this.api.datasets(),
      health:this.api.workerHealth().pipe(catchError(() => of(null))),
      schedules:this.api.effectiveSchedules().pipe(catchError(() => of(null))),
      funnel:this.freshnessApi.get('marketing.sales_funnel','GLOBAL').pipe(catchError(() => of(null))),
      track:this.freshnessApi.get('track.daily','GLOBAL').pipe(catchError(() => of(null)))})
      .pipe(takeUntil(this.destroyed$)).subscribe({
        next:({summary,jobs,datasets,health,schedules,funnel,track})=>{
          this.summary=summary;this.jobs=jobs.jobs;this.datasets=datasets.datasets;this.loading=false;
          this.loadLatestRuns(this.jobs);
          this.configUnavailable=!schedules;
          this.effectiveSchedules=schedules?.jobs??[];
          this.datasetEvidence={'marketing.sales_funnel':funnel,'track.daily':track};
          this.healthUnavailable=!health;this.healthCheckedAt=health?.checked_at_utc??null;
          this.workerHealth=health?.workers??[...new Set(jobs.jobs.map(j=>j.worker_key))].sort()
            .map(worker_key=>({worker_key,status:'UNKNOWN' as const,
              reason_code:'HEALTH_API_UNAVAILABLE',last_seen_at_utc:null,instance_count:0}));
          const selected=this.jobs.find(j=>j.key===this.selected?.key);
          if(selected){this.select(selected);} else{this.close();}
        },
        error:()=>{this.loading=false;this.summary=null;this.jobs=[];this.datasets=[];this.close();
          this.error='No se pudo cargar Control de Automatizaciones.';}
      });
  }
  loadTimeline():void {
    this.tijuanaClock=currentTijuanaClock(new Date());
    if (!this.timelineDate) {return;}
    this.loadingTimeline=true;this.timelineError='';this.timelineWorkers=[];
    this.api.timeline(this.timelineDate).pipe(takeUntil(this.destroyed$)).subscribe({
      next:r=>{this.timelineWorkers=r.workers;this.loadingTimeline=false;},
      error:()=>{this.loadingTimeline=false;this.timelineError='No se pudo consultar la matriz diaria.';}
    });
  }
  timelineRuns(job:TimelineJob,hour:string):TimelineObservation[] {
    return job.observed[hour] || [];
  }
  timelineState(job:TimelineJob,hour:string):ObservationState {
    return classifyObservationRuns(this.timelineRuns(job,hour));
  }
  timelineIcon(job:TimelineJob,hour:string):string {
    const icons:Record<ObservationState,string>={
      completed:'check_circle',replaced:'history',running:'sync',
      partial:'warning_amber',error:'cancel',unknown:'help_outline',
    };
    return icons[this.timelineState(job,hour)];
  }
  timelineObservationTitle(job:TimelineJob,hour:string):string {
    const runs=this.timelineRuns(job,hour);
    const label:Record<ObservationState,string>={
      completed:'Ejecución finalizada. Frescura de datos no verificada',
      replaced:'Versión sustituida, no es fallo',
      running:'Estado RUNNING registrado; actividad actual no verificada',
      partial:'Resultado parcial registrado',
      error:'Fallo registrado',
      unknown:'Estado de ejecución no reconocido',
    };
    return label[this.timelineState(job,hour)]+' · último resultado: '
      +(runs[0]?.status_raw||'desconocido')
      +' · '+runs.length+' ejecución(es) observada(s).';
  }
  referenceIcon(job:TimelineJob,hour:string):string {
    const state=this.referenceState(job,hour);
    return state==='FUTURE_REFERENCE'?'schedule'
      :state==='PAST_REFERENCE_UNVERIFIED'?'help_outline':'';
  }
  showObservation(job:TimelineJob,hour:string):void {
    const runs=this.timelineRuns(job,hour);
    if(!runs.length)return;
    const data: AutomationObservationDialogData = {jobLabel:job.label,jobKey:job.job_key,observation:runs[0]};
    this.dialog.open(AutomationObservationDialogComponent, {data, width:'min(560px, 96vw)', maxWidth:'96vw', autoFocus:false});
  }
  closeObservation():void {this.selectedObservation=null;this.selectedObservationJob='';}
  referenceState(job:TimelineJob,hour:string):ReferenceState {
    return classifyReferenceHour(this.timelineDate,hour,job.reference_slots,this.tijuanaClock);
  }
  referenceTitle(job:TimelineJob,hour:string):string {
    const state=this.referenceState(job,hour);
    if(state==='FUTURE_REFERENCE')return 'Horario de referencia futuro. Todavía no corresponde evaluarlo.';
    if(state==='PAST_REFERENCE_UNVERIFIED')return 'Horario de referencia pasado sin ejecución atribuible. No confirma fallo ni atraso.';
    return 'Sin ejecución observada en esta hora.';
  }
  openLastError(job:Job):void {
    const data:AutomationErrorDialogData={jobKey:job.key,jobLabel:job.label};
    this.dialog.open(AutomationErrorDetailDialogComponent,{
      data,width:'min(610px,96vw)',maxWidth:'96vw',autoFocus:false,
    });
  }
  openRunDiagnostic(run:Run):void {
    if(!this.selected)return;
    const data:AutomationErrorDialogData={
      jobKey:this.selected.key,jobLabel:this.selected.label,runId:run.run_id,
    };
    this.dialog.open(AutomationErrorDetailDialogComponent,{
      data,width:'min(610px,96vw)',maxWidth:'96vw',autoFocus:false,
    });
  }
  canDiagnose(run:Run):boolean {
    return ['FAILED','ERROR','TIMED_OUT','PARTIAL'].includes(run.status_raw.toUpperCase());
  }
  select(job:Job):void {this.selected=job;this.offset=0;this.loadRuns();}
  close():void {this.sequence++;this.selected=null;this.runs=[];this.runsError='';this.loadingRuns=false;}
  pageBy(step:-1|1):void {
    if(this.loadingRuns||(step<0&&this.offset===0)||(step>0&&!this.hasMore))return;
    this.offset=Math.max(0,this.offset+step*this.pageSize);this.loadRuns();
  }
  loadRuns():void {
    if(!this.selected)return;
    const seq=++this.sequence;this.loadingRuns=true;this.runsError='';this.runs=[];this.hasMore=false;
    this.api.runs(this.selected.key,this.offset,this.pageSize).pipe(takeUntil(this.destroyed$)).subscribe({
      next:r=>{if(seq!==this.sequence)return;this.runs=r.rows;this.coverage=r.coverage;
        this.hasMore=r.has_more;this.loadingRuns=false;},
      error:()=>{if(seq!==this.sequence)return;this.loadingRuns=false;this.runsError='No se pudo cargar el historial.';}
    });
  }
  /** Solo el último intento atribuido a cada job; NO es un SLA de datos. */
  private loadLatestRuns(jobs:Job[]):void {
    const sequence=++this.latestRunSequence;
    this.latestRuns={};
    this.latestRunUnavailable={};
    const instrumented=jobs.filter(job=>job.run_history_coverage!=='NOT_INSTRUMENTED');
    from(instrumented).pipe(
      mergeMap(job=>this.api.runs(job.key,0,1).pipe(
        map(response=>({key:job.key,run:response.rows[0]??null,unavailable:false})),
        catchError(()=>of({key:job.key,run:null,unavailable:true})),
      ),4),
      takeUntil(this.destroyed$),
    ).subscribe(({key,run,unavailable})=>{
      if(sequence!==this.latestRunSequence)return;
      this.latestRuns[key]=run;
      if(unavailable)this.latestRunUnavailable[key]=true;
    });
  }
  latestRun(job:Job):Run|null {
    return this.latestRuns[job.key]??null;
  }
  latestRunTime(job:Job):string {
    const run=this.latestRun(job);
    return run
      ? this.formatDate(run.finished_at_utc||run.observed_at_utc||run.started_at_utc)
      : '—';
  }
  latestRunState(job:Job):ObservationState {
    const run=this.latestRun(job);
    return run?classifyObservationRuns([run]):'unknown';
  }
  latestRunStatus(job:Job):string {
    if(job.run_history_coverage==='NOT_INSTRUMENTED')return 'Sin instrumentación';
    if(!(job.key in this.latestRuns))return 'Consultando…';
    if(this.latestRunUnavailable[job.key])return 'No verificable';
    const run=this.latestRun(job);
    if(!run)return 'Sin registro';
    // El audit de reportes solo acredita finalizaciones, no captura fallos.
    if(job.run_history_coverage==='COMPLETION_MARKERS_ONLY')return 'Finalización observada';
    const labels:Record<ObservationState,string>={
      completed:'OK',replaced:'Sustituida',running:'Ejecutando',
      partial:'Parcial',error:'FALLÓ',unknown:'No verificable',
    };
    return labels[this.latestRunState(job)];
  }
  latestRunIsFailure(job:Job):boolean {
    const run=this.latestRun(job);
    return job.run_history_coverage==='DOMAIN_RUNS' &&
      !!run && ['FAILED','ERROR','TIMED_OUT','PARTIAL'].includes(
        run.status_raw.trim().toUpperCase());
  }
  openLatestFailure(job:Job):void {
    const run=this.latestRun(job);
    if(!run||!this.latestRunIsFailure(job))return;
    this.dialog.open(AutomationErrorDetailDialogComponent,{
      data:{jobKey:job.key,jobLabel:job.label,runId:run.run_id},
      width:'min(610px,96vw)',maxWidth:'96vw',autoFocus:false,
    });
  }
  formatDate(value:string|null):string {
    if(!value)return 'Sin registro';
    const date=new Date(value);
    return isNaN(date.getTime())?'Fecha no disponible':date.toLocaleString('es-MX',{timeZone:'America/Tijuana'});
  }
}
