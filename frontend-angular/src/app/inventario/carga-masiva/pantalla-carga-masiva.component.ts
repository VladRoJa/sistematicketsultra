// src/app/inventario/carga-masiva/pantalla-carga-masiva.component.ts

import { Component } from '@angular/core';
import { CommonModule } from '@angular/common';
import { MatTabsModule } from '@angular/material/tabs';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { CargaMasivaArchivoComponent } from './carga-masiva-archivo.component';

@Component({
  selector: 'app-pantalla-carga-masiva',
  standalone: true,
  imports: [
    CommonModule,
    MatTabsModule,
    MatButtonModule,
    MatCardModule,
    CargaMasivaArchivoComponent
  ],
  templateUrl: './pantalla-carga-masiva.component.html',
  styleUrls: ['./pantalla-carga-masiva.component.css']
})
export class PantallaCargaMasivaComponent {
  vista: 'manual' | 'directa' = 'manual';
  selectedIndex = 0;

  cambiarVista(nueva: 'manual' | 'directa') {
    this.vista = nueva;
    this.selectedIndex = nueva === 'manual' ? 0 : 1;
  }

  onTabChange(idx: number) {
    this.selectedIndex = idx;
    this.vista = idx === 0 ? 'manual' : 'directa';
  }
}
