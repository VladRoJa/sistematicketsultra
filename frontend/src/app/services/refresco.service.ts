// src/app/services/refresco.service.ts



import { Injectable } from '@angular/core';
import { Subject } from 'rxjs';

@Injectable({ providedIn: 'root' })
export class RefrescoService {
  private refrescarTablaSubject = new Subject<void>();
  refrescarTabla$ = this.refrescarTablaSubject.asObservable();

  private refrescarResumenValidacionTicketsSubject = new Subject<void>();
  refrescarResumenValidacionTickets$ =
    this.refrescarResumenValidacionTicketsSubject.asObservable();

  emitirRefresco(): void {
    this.refrescarTablaSubject.next();
  }

  emitirRefrescoResumenValidacionTickets(): void {
    this.refrescarResumenValidacionTicketsSubject.next();
  }
}