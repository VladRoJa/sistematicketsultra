//ticket.service.ts

import { Injectable } from '@angular/core';
import { HttpClient, HttpHeaders } from '@angular/common/http';
import { Observable } from 'rxjs';

@Injectable({
  providedIn: 'root'
})
export class TicketService {
  private apiUrl = 'http://localhost:5000/api/tickets';  // URL del backend

  constructor(private http: HttpClient) {}

  getTickets(): Observable<any> {
    const token = localStorage.getItem('token');

    if (!token) {
      console.error("❌ No hay token en localStorage.");
      return new Observable();
    }

    const headers = new HttpHeaders()
      .set('Authorization', `Bearer ${token}`)
      .set('Content-Type', 'application/json');

    return this.http.get<any>(this.apiUrl, { headers, withCredentials: true });
  }
}
