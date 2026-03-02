// frontend/src/app/services/auth.service.ts

import { Injectable } from '@angular/core';
import { HttpClient, HttpHeaders } from '@angular/common/http';
import { Observable, throwError, of } from 'rxjs';
import { Router } from '@angular/router';
import { tap, shareReplay, finalize } from 'rxjs/operators';
import { NoAuthHttpClient } from './no-auth-http-client.service';
import { environment } from '../../environments/environment';
import { SessionService } from '../core/auth/session.service';



@Injectable({
  providedIn: 'root'
})
export class AuthService {
  private apiUrl = `${environment.apiUrl}/auth`;
  private sessionInfoRequest$?: Observable<any>;

  
  constructor(
    private http: HttpClient,
    private router: Router,
    private noAuthHttp: NoAuthHttpClient,
    private session: SessionService,
  ) {}

  login(username: string, password: string): Observable<any> {
    console.log("🚀 Enviando login con credenciales:");

    return this.http.post<any>(
      `${this.apiUrl}/login`,
      { username, password },
      { withCredentials: true }
    ).pipe(
      tap({
        next: (response) => {
          console.log("✅ Respuesta del backend:", response);
        },
        error: (error) => {
          console.error("❌ Error recibido del backend:", error);
        }
      })
    );
  }

  logout() {
    console.log("🚪 Cerrando sesión...");
    this.session.clearSession(); // ✅ antes: localStorage.removeItem(...)
    console.log("✅ Sesión eliminada.");
    this.router.navigate(['/login']);
  }

  setSession(token: string, user: any, redirigir: boolean = true) {
    console.log("📌 setSession() EJECUTADO");
    console.log("📌 Guardando usuario en sesión:", user);

    this.session.setSession(token, user || {}); // ✅ antes: localStorage.setItem...

    const storedUser = this.session.getUser();
    console.log("🔍 Usuario después de guardar:", storedUser);

    if (!redirigir) return;

    // 📌 Redirigir según el área del usuario
    const area = user?.sucursal_id;
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
    return this.session.getToken(); // ✅ antes: localStorage.getItem('token')
  }

  getUser(): any {
    const user = this.session.getUser(); // ✅ antes: parse manual
    if (!user) {
      console.warn("⚠️ No hay usuario en sesión.");
      return null;
    }
    return user;
  }

  isLoggedIn(): boolean {
    return this.session.isLoggedIn(); // ✅ antes: !!getToken()
  }

  obtenerUsuarioAutenticado(): Observable<any> {
    const token = this.getToken();
    if (!token) {
      console.warn("⚠️ No hay token disponible, no se puede obtener la sesión.");
      return throwError(() => new Error("No hay token disponible"));
    }

    // ✅ Si ya tenemos usuario en sesión, no pegamos al backend otra vez.
    const existingUser = this.getUser();
    if (existingUser) {
      return of({ user: existingUser });
    }

    // ✅ Si ya hay una petición en curso, reutilízala.
    if (this.sessionInfoRequest$) {
      return this.sessionInfoRequest$;
    }

    const headers = new HttpHeaders().set("Authorization", `Bearer ${token}`);

    this.sessionInfoRequest$ = this.http
      .get<any>(`${environment.apiUrl}/session-info`, { headers })
      .pipe(
        tap(response => {
          if (response?.user) {
            console.log("📌 Usuario obtenido de la API:", response.user);
            this.setSession(token, response.user);
          }
        }),
        // ✅ cachea el resultado para los subscriptores simultáneos
        shareReplay(1),
        // ✅ al terminar (éxito o error) liberamos el “lock”
        finalize(() => {
          this.sessionInfoRequest$ = undefined;
        }),
      );

    return this.sessionInfoRequest$;
  }

  esAdmin(): boolean {
    // Puedes usar session.isAdmin(), pero lo dejo equivalente a tu lógica actual:
    const user = this.getUser();
    if (!user) return false;
    const rol = (user.rol || '').toLowerCase();
    return rol === 'administrador' || rol === 'super_admin';
  }

  esLectorGlobal(): boolean {
    const user = this.getUser();
    if (!user) return false;
    const rol = (user.rol || '').toUpperCase();
    return rol === 'LECTOR_GLOBAL';
  }

  esGerente(): boolean {
    const user = this.getUser();
    if (!user) return false;
    const rol = (user.rol || '').toUpperCase();
    return rol === 'GERENTE';
  }
}