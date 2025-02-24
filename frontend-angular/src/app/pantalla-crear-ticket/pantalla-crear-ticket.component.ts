//pantalla-crear-ticket.ts

import { Component } from '@angular/core';
import { HttpClient, HttpHeaders, HttpClientModule } from '@angular/common/http';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { Router } from '@angular/router';

@Component({
  selector: 'app-pantalla-crear-ticket',
  standalone: true,
  imports: [CommonModule, FormsModule, HttpClientModule], // Agregar HttpClientModule
  templateUrl: './pantalla-crear-ticket.component.html',
  styleUrls: ['./pantalla-crear-ticket.component.css']
})
export class PantallaCrearTicketComponent {
  titulo: string = '';
  descripcion: string = '';
  usuario: string = ''; 
  mensaje: string = '';

  private apiUrl = 'http://localhost:5000/api/tickets'; 

  constructor(private http: HttpClient, private router: Router) {}

  onSubmit() {
    if (!this.titulo || !this.descripcion) {
      this.mensaje = "⚠️ Por favor, llena todos los campos.";
      return;
    }

    const token = localStorage.getItem('token'); 
    console.log("🔑 Token enviado:", token); // 🚀 Verifica que el token no sea `null`
    
    const headers = token
     ? new HttpHeaders().set('Authorization', `Bearer ${token}`)
     : new HttpHeaders();
    
    const nuevoTicket = {
      titulo: this.titulo.trim(),
      descripcion: this.descripcion.trim(),
    };

    this.http.post<{ mensaje: string }>(this.apiUrl, nuevoTicket, { headers }).subscribe({
      next: (response) => {
        console.log("✅ Ticket creado:", response);
        this.mensaje = "✅ Ticket creado correctamente.";
        
        // Retraso para UX antes de redirigir
        setTimeout(() => {
          this.titulo = "";
          this.descripcion = "";
          this.mensaje = "";
      }, 1000);
      },
      error: (error) => {
        console.error("❌ Error al crear el ticket:", error);
        console.log("🔍 Código de error recibido:", error.status);
        console.log("📌 Respuesta completa:", error);

        if (error.status === 400) {
          this.mensaje = "⚠️ Faltan datos obligatorios.";
        } else if (error.status === 401) {
          console.warn("🔍 Intento de redirección a /login desde error 401");
          console.trace(); // 🔥 Esto mostrará qué código llamó esta línea
          this.mensaje = "🔒 No autorizado, inicia sesión.";
          setTimeout(() => this.router.navigate(['/login']), 1500);
      
        } else {
          this.mensaje = "❌ Error interno en el servidor.";
        }
      }
    });
  }
}
