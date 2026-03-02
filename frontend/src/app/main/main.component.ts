// src/app/main/main.component.ts

import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterOutlet, Router } from '@angular/router';
import { FormsModule } from '@angular/forms';
import { NgxPaginationModule } from 'ngx-pagination';
import { mostrarAlertaToast } from '../utils/alertas';
import { SessionService } from '../core/auth/session.service';

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
  usuarioInfo = "Usuario";
  esAdmin = false;

  constructor(
    private router: Router,
    private session: SessionService,
  ) {}

  ngOnInit() {
    this.cargarUsuarioDesdeSesion();
  }

  private cargarUsuarioDesdeSesion(): void {
    const user = this.session.getUser();
    this.usuarioInfo = user?.username || "Usuario";
    this.esAdmin = this.session.isAdmin();
  }

  cerrarSesion() {
    this.session.clearSession();
    this.router.navigate(['/login']);
  }

  irAGestionPermisos() {
    if (!this.session.isLoggedIn()) {
      mostrarAlertaToast("Se requiere autenticación.");
      this.router.navigate(['/login']);
      return;
    }

    this.router.navigate(['/admin-permisos']).then(success => {
      if (!success) console.error("Fallo la navegación a /admin-permisos");
    }).catch(error => {
      console.error("Error en la navegación:", error);
    });
  }
}