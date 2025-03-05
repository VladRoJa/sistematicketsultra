//auth.service.ts

import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';
import { Router } from '@angular/router';

@Injectable({
  providedIn: 'root'
})
export class AuthService {
  private apiUrl = 'http://localhost:5000/api/auth';

  constructor(private http: HttpClient, private router: Router) { }

  login(username: string, password: string): Observable<any> {  // 🔹 Debe devolver un Observable
    return this.http.post<any>(`${this.apiUrl}/login`, { username, password });
  }

  logout() {
    localStorage.removeItem('token');
    localStorage.removeItem('user');
    this.router.navigate(['/login']);
  }

  setSession(token: string, user: any) {
    localStorage.setItem('token', token);
    localStorage.setItem('user', JSON.stringify(user));

    // 📌 Redirigir según el área del usuario
    const area = user.id_sucursal;
    if (area === 1) this.router.navigate(['/tickets/mantenimiento']);
    else if (area === 2) this.router.navigate(['/tickets/finanzas']);
    else if (area === 3) this.router.navigate(['/tickets/marketing']);
    else if (area === 4) this.router.navigate(['/tickets/gerencia-deportiva']);
    else if (area === 5) this.router.navigate(['/tickets/recursos-humanos']);
    else if (area === 6) this.router.navigate(['/tickets/compras']);
    else if (area === 7) this.router.navigate(['/tickets/sistemas']);
    else this.router.navigate(['/']);
  }

  getToken(): string | null {
    return localStorage.getItem('token');
  }

  getUser(): any {
    const user = localStorage.getItem('user');
    return user ? JSON.parse(user) : null;
  }

  isLoggedIn(): boolean {
    return !!this.getToken();
  }

  obtenerUsuarioAutenticado(): Observable<any> {
    const token = this.getToken();
    if (!token) {
      console.warn("⚠️ No hay token disponible, no se puede obtener la sesión.");
      return new Observable((observer) => {
        observer.error("No hay token disponible");
      });
    }
  
    const headers = { Authorization: `Bearer ${token}` };
  
    return this.http.get<any>(`${this.apiUrl}/session-info`, { headers });
  }
  
}
