import { CommonModule } from '@angular/common';
import { Component, OnDestroy, OnInit } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { forkJoin, Subject, takeUntil } from 'rxjs';
import { AutomationControlService } from './automation-control.service';
import { Job, Run, Summary, Dataset } from './automation-control.models';

@Component({ selector:'app-automation-control',standalone:true,imports:[CommonModule,FormsModule],
  templateUrl:'./automation-control.component.html',styleUrls:['./automation-control.component.css'] })
export class AutomationControlComponent implements OnInit,OnDestroy {
  readonly pageSize=20;
  private readonly destroyed$=new Subject<void>();
  private sequence=0;
  summary:Summary|null=null; jobs:Job[]=[]; datasets:Dataset[]=[];
  selected:Job|null=null; runs:Run[]=[]; coverage='UNKNOWN'; offset=0; hasMore=false;
  domain=''; search=''; loading=true; loadingRuns=false; error=''; runsError='';
  constructor(private readonly api:AutomationControlService){}
  ngOnInit():void { this.refresh(); }
  ngOnDestroy():void { this.destroyed$.next();this.destroyed$.complete(); }
  get domains():string[] {return [...new Set(this.jobs.map(j=>j.domain))].sort();}
  get visibleJobs():Job[] {
    const text=this.search.trim().toLowerCase();
    return this.jobs.filter(j=>(!this.domain||j.domain===this.domain)&&
      (!text||[j.label,j.key,j.worker_key].some(v=>v.toLowerCase().includes(text))));
  }
  get page():number {return Math.floor(this.offset/this.pageSize)+1;}
  refresh():void {
    this.sequence++;this.loading=true;this.error='';
    forkJoin({summary:this.api.summary(),jobs:this.api.jobs(),datasets:this.api.datasets()})
      .pipe(takeUntil(this.destroyed$)).subscribe({
        next:({summary,jobs,datasets})=>{
          this.summary=summary;this.jobs=jobs.jobs;this.datasets=datasets.datasets;this.loading=false;
          const selected=this.jobs.find(j=>j.key===this.selected?.key);
          if(selected){this.select(selected);} else{this.close();}
        },
        error:()=>{this.loading=false;this.summary=null;this.jobs=[];this.datasets=[];this.close();
          this.error='No se pudo cargar Control de Automatizaciones.';}
      });
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
  formatDate(value:string|null):string {
    if(!value)return 'Sin registro';
    const date=new Date(value);
    return isNaN(date.getTime())?'Fecha no disponible':date.toLocaleString('es-MX',{timeZone:'America/Tijuana'});
  }
}
