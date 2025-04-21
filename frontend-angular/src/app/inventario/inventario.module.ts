// src/app/inventario/inventario.module.ts

import { NgModule } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterModule } from '@angular/router';
import { ReactiveFormsModule, FormsModule } from '@angular/forms';

// Rutas
import { InventarioRoutingModule } from './inventario-routing.module';

// Angular Material
import { MatIconModule } from '@angular/material/icon';
import { MatButtonModule } from '@angular/material/button';
import { MatTableModule } from '@angular/material/table';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatSelectModule } from '@angular/material/select';
import { MatCardModule } from '@angular/material/card';

// Componentes Standalone (importar en lugar de declarar)
import { InventarioLayoutComponent } from './inventario-layout/inventario-layout.component';
import { ProductosComponent } from './productos/productos.component';
import { MovimientosComponent } from './movimientos/movimientos.component';
import { ReportesComponent } from './reportes/reportes.component';

@NgModule({
  imports: [
    CommonModule,
    RouterModule,
    InventarioRoutingModule,
    FormsModule,
    ReactiveFormsModule,

    // Angular Material
    MatIconModule,
    MatButtonModule,
    MatTableModule,
    MatFormFieldModule,
    MatInputModule,
    MatSelectModule,
    MatCardModule,


    // Standalone components
    InventarioLayoutComponent,
    ProductosComponent,
    MovimientosComponent,
    ReportesComponent,
  ],
})
export class InventarioModule {}
