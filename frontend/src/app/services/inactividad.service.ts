// src/app/services/inactividad.service.ts
import { Injectable } from '@angular/core';

@Injectable({ providedIn: 'root' })
export class InactividadService {
  private callbackReiniciar: (() => void) | null = null;

  registrarCallback(cb: () => void) {
    this.callbackReiniciar = cb;
  }

  reiniciarTemporizador() {
    if (this.callbackReiniciar) {
      this.callbackReiniciar();
    }
  }
}
