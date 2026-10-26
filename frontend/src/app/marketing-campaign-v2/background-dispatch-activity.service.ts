import { Injectable } from '@angular/core';
import { Subject } from 'rxjs';

/** In-memory GET-refresh hints only; stores no credentials or recipient data. */
@Injectable({ providedIn: 'root' })
export class BackgroundDispatchActivityService {
  private readonly changed = new Subject<void>();
  readonly changes$ = this.changed.asObservable();
  notifyChanged(): void { this.changed.next(); }
}
