// src/app/pantalla-login/pantalla-login.component.ts

import { Component } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { AuthService } from '../services/auth.service';
import { Router } from '@angular/router';
import { LoaderComponent } from '../shared/loader/loader.component'; 

@Component({
  selector: 'app-login',
  standalone: true,
  imports: [CommonModule, FormsModule, LoaderComponent],
  templateUrl: './pantalla-login.component.html',
  styleUrls: ['./pantalla-login.component.css']
})
export class LoginComponent {
  username = '';
  password = '';
  errorMessage = '';
  cargando = false;

  constructor(
    private authService: AuthService,
    private router: Router
  ) {}

onSubmit(): void {
  if (!this.username || !this.password) {
    this.errorMessage = "⚠️ Por favor, ingresa usuario y contraseña.";
    return;
  }

  this.errorMessage = '';

  this.authService.login(this.username, this.password).subscribe({
    next: (response) => this.handleLoginSuccess(response),
    error: (error) => this.handleLoginError(error)
  });
}

private handleLoginSuccess(response: any): void {
  console.log("✅ Respuesta del backend:", response);
  if (response?.token && response?.user) {
    console.log("📌 Usuario autenticado:", response.user);

    this.cargando = true; // 🔹 Activar loader SOLO si es login correcto
    this.authService.setSession(response.token, response.user);

    const username = String(
      response.user?.username || ''
    )
      .trim()
      .toUpperCase();

    setTimeout(() => {
      this.router.navigate([
        username === 'ADMICORP'
          ? '/control'
          : '/main',
      ]);
    }, 2000);

  } else {
    this.errorMessage = "⚠️ Error inesperado: Token o usuario no recibido.";
  }
}

private handleLoginError(error: any): void {
  console.error("❌ Error en el login:", error);
  this.cargando = false;

  switch (error.status) {
    case 0:
      this.errorMessage = "🚨 No se pudo conectar con el servidor.";
      break;
    case 401:
      this.errorMessage = "⚠️ Credenciales incorrectas, intenta de nuevo.";
      break;
    case 500:
      this.errorMessage = "❌ Error interno en el servidor.";
      break;
    default:
      this.errorMessage = "❓ Error desconocido.";
  }
}

}
