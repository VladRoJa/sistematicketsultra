//auth.service.ts

import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';

@Injectable({
  providedIn: 'root' // Esto hace que el servicio esté disponible en toda la app
})
export class AuthService {
  private apiUrl = 'http://localhost:5000/api/auth/login';

  constructor(private http: HttpClient) { }

  login(credentials: { usuario: string; password: string }): Observable<any> {
    return this.http.post<any>(this.apiUrl, credentials, { withCredentials: true });
  }
}
