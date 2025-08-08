// src/app/pantalla-inicio/pantalla-inicio.component.ts

import { Component } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';

@Component({
  selector: 'app-pantalla-inicio',
  standalone: true,
  templateUrl: './pantalla-inicio.component.html',
  styleUrls: ['./pantalla-inicio.component.css']
})
export class PantallaInicioComponent {
  // Aquí podrás agregar variables dinámicas a futuro
  usuarioNombre: string = '';

  constructor() {
    const userString = localStorage.getItem('user');
    if (userString) {
      const user = JSON.parse(userString);
      this.usuarioNombre = user.nombre || 'Usuario';
    }
  }
}
