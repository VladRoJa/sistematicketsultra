import { Component } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { AuthService } from '../services/auth.service';
import { Router } from '@angular/router';

@Component({
  selector: 'app-login',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './pantalla-login.component.html',
  styleUrls: ['./pantalla-login.component.css']
})
export class LoginComponent { 
  usuario: string = "";
  password: string = "";
  errorMessage: string = "";

  constructor(private authService: AuthService, private router: Router) {}

  onSubmit() {
    this.authService.login({ usuario: this.usuario, password: this.password })
      .subscribe({
        next: (response) => {
          console.log("✅ Respuesta del backend:", response);
          if (response && response.token) {
            localStorage.setItem('token', response.token); // Guardamos el token de sesión
            this.router.navigate(['/main']); // Redirigimos a la pantalla principal
          } else {
            this.errorMessage = "⚠️ Error inesperado: Token no recibido.";
          }
        },
        error: (error) => {
          console.error("❌ Error en el login:", error);
          if (error.status === 0) {
            this.errorMessage = "🚨 No se pudo conectar con el servidor.";
          } else if (error.status === 401) {
            this.errorMessage = "⚠️ Credenciales incorrectas, intenta de nuevo.";
          } else if (error.status === 500) {
            this.errorMessage = "❌ Error interno en el servidor.";
          } else {
            this.errorMessage = "❓ Error desconocido.";
          }
        }
      });
  }
}
