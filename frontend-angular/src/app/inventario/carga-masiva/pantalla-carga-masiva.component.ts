//C:\Users\Vladimir\Documents\Sistema tickets\frontend-angular\src\app\inventario\carga-masiva\pantalla-carga-masiva.component.ts

import { Component } from '@angular/core';
import { CommonModule } from '@angular/common';
import { CargaMasivaComponent } from './carga-masiva.component';
import { CargaMasivaSinMapeoComponent } from './carga-masiva-sinmapeo.component';

@Component({
  selector: 'app-pantalla-carga-masiva',
  standalone: true,
  imports: [CommonModule, CargaMasivaComponent, CargaMasivaSinMapeoComponent],
  templateUrl: './pantalla-carga-masiva.component.html',
  styleUrls: ['./pantalla-carga-masiva.component.css']
})
export class PantallaCargaMasivaComponent {
  vista: 'manual' | 'directa' = 'manual';

  cambiarVista(nueva: 'manual' | 'directa') {
    this.vista = nueva;
  }
}
