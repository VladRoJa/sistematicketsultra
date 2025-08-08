// src/app/services/sucursales.service.ts
import { Injectable } from '@angular/core';
import { HttpClient, HttpHeaders } from '@angular/common/http';
import { environment } from 'src/environments/environment';

@Injectable({ providedIn: 'root' })
export class SucursalesService {
  private apiUrl = `${environment.apiUrl}/inventario/sucursales`;
  constructor(private http: HttpClient) {}
  obtenerSucursales() {
    const token = localStorage.getItem('token');
    const headers = token ? new HttpHeaders().set('Authorization', `Bearer ${token}`) : new HttpHeaders();
    return this.http.get<any[]>(this.apiUrl, { headers });
  }
}
