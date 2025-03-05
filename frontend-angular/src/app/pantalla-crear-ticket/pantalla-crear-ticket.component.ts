//pantalla-crear-ticket.ts

import { Component, OnInit } from '@angular/core';
import { HttpClient, HttpHeaders } from '@angular/common/http';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { Router } from '@angular/router';

@Component({
  selector: 'app-pantalla-crear-ticket',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './pantalla-crear-ticket.component.html',
  styleUrls: ['./pantalla-crear-ticket.component.css']
})
export class PantallaCrearTicketComponent implements OnInit {
  titulo: string = '';
  descripcion: string = '';
  departamento: number | null = null;
  criticidad: number | null = null;
  mensaje: string = '';

  departamentos = [
    { id: 1, nombre: 'Mantenimiento' },
    { id: 2, nombre: 'Finanzas' },
    { id: 3, nombre: 'Marketing' },
    { id: 4, nombre: 'Gerencia Deportiva' },
    { id: 5, nombre: 'Recursos Humanos' },
    { id: 6, nombre: 'Compras' },
    { id: 7, nombre: 'Sistemas' }
  ];

  private apiUrl = 'http://localhost:5000/api/tickets/create'; 

  constructor(private http: HttpClient, private router: Router) {}

  ngOnInit() {}

  onSubmit() {
    if (!this.titulo || !this.descripcion || !this.departamento || !this.criticidad) {
      this.mensaje = "⚠️ Por favor, llena todos los campos.";
      return;
    }

    const token = localStorage.getItem('token');
    const headers = token
      ? new HttpHeaders().set('Authorization', `Bearer ${token}`)
      : new HttpHeaders();
    
    const nuevoTicket = {
      titulo: this.titulo.trim(),
      descripcion: this.descripcion.trim(),
      departamento_id: this.departamento,
      criticidad: this.criticidad
    };

    this.http.post<{ mensaje: string }>(this.apiUrl, nuevoTicket, { headers }).subscribe({
      next: (response) => {
        this.mensaje = "✅ Ticket creado correctamente.";
        setTimeout(() => {
          this.titulo = "";
          this.descripcion = "";
          this.departamento = null;
          this.criticidad = null;
          this.mensaje = "";
        }, 1000);
      },
      error: (error) => {
        if (error.status === 400) {
          this.mensaje = "⚠️ Faltan datos obligatorios.";
        } else if (error.status === 401) {
          this.mensaje = "🔒 No autorizado, inicia sesión.";
          setTimeout(() => this.router.navigate(['/login']), 1500);
        } else {
          this.mensaje = "❌ Error interno en el servidor.";
        }
      }
    });
  }
}
