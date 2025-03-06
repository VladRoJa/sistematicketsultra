//main.componets.ts

import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterLink, RouterOutlet, Router } from '@angular/router';
import { HttpClient, HttpHeaders } from '@angular/common/http';
import { FormsModule } from '@angular/forms';
import { NgxPaginationModule } from 'ngx-pagination';


@Component({
  selector: 'app-main',
  standalone: true,
  imports: [CommonModule, RouterLink, RouterOutlet, FormsModule, NgxPaginationModule],
  templateUrl: './main.component.html',
  styleUrls: ['./main.component.css']
})
export class MainComponent implements OnInit {
  usuarioInfo = "Usuario"; // Almacena el nombre del usuario autenticado
  esAdmin = false; // 🔥 Controla si el usuario es administrador
  mostrarEliminarTicket = false; // Controla la visibilidad del cuadro de eliminación
  idTicketEliminar: number | null = null; // Almacena el ID del ticket a eliminar

  private apiUrl = 'http://localhost:5000/api/tickets'; // URL de tickets
  private authUrl = 'http://localhost:5000/api/auth/session-info'; // URL de autenticación

  constructor(private router: Router, private http: HttpClient) {}

  ngOnInit() {
    this.obtenerUsuarioAutenticado();
  }

  // ✅ Obtener información del usuario autenticado
  obtenerUsuarioAutenticado() {
    const token = localStorage.getItem('token');
    if (!token) {
      console.warn("⚠️ No hay token, el usuario no está autenticado.");
      return;
    }

    const headers = new HttpHeaders()
      .set('Authorization', `Bearer ${token}`)
      .set('Content-Type', 'application/json');

    this.http.get<{ user: any }>(this.authUrl, { headers }).subscribe({
      next: (response) => {
        if (response?.user) {
          this.usuarioInfo = response.user.username;
          this.esAdmin = response.user.rol === "ADMINISTRADOR"; // ✅ Verifica si es administrador
        }
      },
      error: (error) => {
        console.error("❌ Error obteniendo usuario autenticado:", error);
      }
    });
  }

  // ✅ Función para eliminar tickets
  eliminarTicket() {
    if (!this.idTicketEliminar) {
      alert("⚠️ Debes ingresar un ID de ticket.");
      return;
    }

    const token = localStorage.getItem('token');
    if (!token) {
      console.error("❌ No hay token, no se puede eliminar el ticket.");
      return;
    }

    if (!confirm(`❌ ¿Estás seguro de eliminar el ticket #${this.idTicketEliminar}? Esta acción no se puede deshacer.`)) {
      return;
    }

    const headers = new HttpHeaders().set('Authorization', `Bearer ${token}`).set('Content-Type', 'application/json');

    this.http.delete(`${this.apiUrl}/delete/${this.idTicketEliminar}`, { headers }).subscribe({
      next: (response: any) => {
        console.log(`✅ Ticket ${this.idTicketEliminar} eliminado.`);
        alert(response.mensaje);
        this.idTicketEliminar = null;
        this.mostrarEliminarTicket = false;
      },
      error: (error) => {
        console.error(`❌ Error al eliminar el ticket:`, error);
        alert("❌ No se pudo eliminar el ticket.");
      }
    });
  }

  cerrarSesion(origen: string = "manual") {
    console.warn(`🚨 Se ejecutó cerrarSesion() automáticamente desde: ${origen}`);
    console.trace();
    localStorage.removeItem('token'); // ✅ Eliminar el token
    this.router.navigate(['/login']); // ✅ Redirigir a login
  }
}
