// src/app/services/refresco.service.ts
import { Injectable } from '@angular/core';
import { Subject } from 'rxjs';

@Injectable({ providedIn: 'root' })
export class RefrescoService {
  private refrescarTablaSubject = new Subject<void>();
  refrescarTabla$ = this.refrescarTablaSubject.asObservable();

  emitirRefresco() {
    this.refrescarTablaSubject.next();
  }
}
