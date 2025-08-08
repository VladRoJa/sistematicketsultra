//no-auth-http-client.service.ts

import { Injectable } from '@angular/core';
import { HttpClient, HttpBackend } from '@angular/common/http';

@Injectable({ providedIn: 'root' })
export class NoAuthHttpClient extends HttpClient {
  constructor(handler: HttpBackend) {
    // Llama al constructor de HttpClient con el "handler" por defecto (sin interceptores)
    super(handler);
  }
}