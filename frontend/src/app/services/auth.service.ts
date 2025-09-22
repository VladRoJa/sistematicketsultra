//auth.service.ts

import { Injectable } from '@angular/core';
import { HttpClient, HttpHeaders } from '@angular/common/http';
import { Observable, throwError } from 'rxjs';
import { Router } from '@angular/router';
import { tap } from 'rxjs/operators';
import { NoAuthHttpClient } from './no-auth-http-client.service';
import { environment } from '../../environments/environment'; 

@Injectable({
  providedIn: 'root'
})
export class AuthService {
  private apiUrl = `${environment.apiUrl}/auth`;

  constructor(private http: HttpClient, private router: Router, private noAuthHttp: NoAuthHttpClient) { }

  login(username: string, password: string): Observable<any> {
    console.log("🚀 Enviando login con credenciales:");
    console.log("👤 Usuario:", username);
    console.log("🔑 Contraseña:", password);
  
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
    localStorage.removeItem('token');
    localStorage.removeItem('user');
    console.log("✅ Sesión eliminada.");
    this.router.navigate(['/login']);
}


setSession(token: string, user: any, redirigir: boolean = true) {

    console.log("📌 setSession() EJECUTADO"); 
    console.log("📌 Guardando usuario en localStorage:", user);
    localStorage.setItem('token', token);
    localStorage.setItem('user', JSON.stringify(user));
    const storedUser = localStorage.getItem('user');
    console.log("🔍 Usuario después de guardar:", storedUser ? JSON.parse(storedUser) : null);

    if (!redirigir) return;

    // 📌 Redirigir según el área del usuario
    const area = user.sucursal_id;
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
    const userString = localStorage.getItem("user");

    if (!userString) {
        console.warn("⚠️ No hay usuario en localStorage.");
        return null;
    }

    try {
        const user = JSON.parse(userString);
        return user;
    } catch (error) {
        console.error("❌ Error al parsear usuario desde localStorage:", error);
        return null;
    }
}


  isLoggedIn(): boolean {
    return !!this.getToken();
  }

  obtenerUsuarioAutenticado(): Observable<any> {
    const token = this.getToken();
    if (!token) {
      console.warn("⚠️ No hay token disponible, no se puede obtener la sesión.");
      return throwError(() => new Error("No hay token disponible"));
    }
  
    const headers = new HttpHeaders().set("Authorization", `Bearer ${token}`);
  
    return this.http.get<any>(`${this.apiUrl}/session-info`, { headers }).pipe(
      tap(response => {
        if (response?.user) {
          console.log("📌 Usuario obtenido de la API:", response.user);
          this.setSession(token, response.user); // 🔥 Ahora se guarda en localStorage al obtener la sesión
        }
      })
    );
  }
  
    esAdmin(): boolean {
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
