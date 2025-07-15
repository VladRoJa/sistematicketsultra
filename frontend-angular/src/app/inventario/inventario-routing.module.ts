// src/app/inventario/inventario-routing.module.ts

import { NgModule } from '@angular/core';
import { RouterModule, Routes } from '@angular/router';
import { InventarioLayoutComponent } from './inventario-layout/inventario-layout.component';
import { InventarioComponent } from './inventario.component'; // <-- Nuevo componente principal de inventario
import { MovimientosComponent } from './movimientos/movimientos.component';
import { ReportesComponent } from './reportes/reportes.component';
import { ExistenciasComponent } from './existencias/existencias.component';

const routes: Routes = [
  {
    path: '',
    component: InventarioLayoutComponent,
    children: [
      { path: '', component: InventarioComponent },
      { path: 'inventario', component: InventarioComponent },    // ← Nuevo listado de inventario
      { path: 'movimientos', component: MovimientosComponent },
      { path: 'reportes', component: ReportesComponent },
      { path: 'existencias', component: ExistenciasComponent },
    ],
  },
];

@NgModule({
  imports: [RouterModule.forChild(routes)],
  exports: [RouterModule],
})
export class InventarioRoutingModule {}
