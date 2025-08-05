//src\app\main\main.component.ts

import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterLink, RouterOutlet, Router } from '@angular/router';
import { HttpClient, HttpHeaders } from '@angular/common/http';
import { FormsModule } from '@angular/forms';
import { NgxPaginationModule } from 'ngx-pagination';
import { environment } from 'src/environments/environment'; // Importa la configuración del entorno
import { mostrarAlertaErrorDesdeStatus, mostrarAlertaToast } from '../utils/alertas';

@Component({
  selector: 'app-main',
  standalone: true,
  imports: [
    CommonModule,
    RouterOutlet,
    FormsModule,
    NgxPaginationModule
  ],
  templateUrl: './main.component.html',
  styleUrls: ['./main.component.css']
})
export class MainComponent implements OnInit {
  usuarioInfo = "Usuario";  // Almacena el nombre del usuario autenticado
  esAdmin = false;          // Controla si el usuario es administrador

  private authUrl = `${environment.apiUrl}/auth/session-info`; // URL de autenticación

  constructor(private router: Router, private http: HttpClient) {}

  ngOnInit() {
    this.obtenerUsuarioAutenticado();
  }

  // Método para obtener la información del usuario autenticado
  obtenerUsuarioAutenticado() {
    const token = localStorage.getItem('token');
    if (!token) {
      console.warn("No hay token, el usuario no está autenticado.");
      return;
    }

    const headers = new HttpHeaders()
      .set('Authorization', `Bearer ${token}`)
      .set('Content-Type', 'application/json');

    this.http.get<{ user: any }>(this.authUrl, { headers }).subscribe({
      next: (response) => {
        if (response?.user) {
          this.usuarioInfo = response.user.username;
          this.esAdmin = response.user.rol === "ADMINISTRADOR";
        }
      },
      error: (error) => {
        console.error("Error obteniendo usuario autenticado:", error);
      }
    });
  }

  // Función para cerrar sesión
  cerrarSesion() {
    localStorage.removeItem('token');
    this.router.navigate(['/login']);
  }

  // Función para navegar a la gestión de permisos (solo para admin)
  irAGestionPermisos() {
    const token = localStorage.getItem('token');
    if (!token) {
      mostrarAlertaToast("Token no encontrado. Se requiere autenticación.");
      this.router.navigate(['/login']);
      return;
    }
    this.router.navigate(['/admin-permisos']).then(success => {
      if (!success) {
        console.error("Fallo la navegación a /admin-permisos");
      }
    }).catch(error => {
      console.error("Error en la navegación:", error);
    });
  }
}
