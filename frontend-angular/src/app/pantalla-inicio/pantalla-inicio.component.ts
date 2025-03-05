//pantalla-inicio.componets.ts

import { Component } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';

@Component({
  selector: 'app-pantalla-inicio',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './pantalla-inicio.component.html',
  styleUrls: ['./pantalla-inicio.component.css'] // Corregido aquí
})
export class PantallaInicioComponent {

}