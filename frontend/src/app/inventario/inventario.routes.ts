//frontend-angular\src\app\inventario\inventario.routes.ts

import { Routes } from '@angular/router';
import { InventarioLayoutComponent } from './inventario-layout/inventario-layout.component';
import { InventarioComponent } from './inventario.component';
import { MovimientosComponent } from './movimientos/movimientos.component';
import { ReportesComponent } from './reportes/reportes.component';
import { ExistenciasComponent } from './existencias/existencias.component';

export const INVENTARIO_ROUTES: Routes = [
  {
    path: '',
    component: InventarioLayoutComponent,
    children: [
      { path: '', component: InventarioComponent },          // Vista principal
      { path: 'inventario', component: InventarioComponent },
      { path: 'movimientos', component: MovimientosComponent },
      { path: 'reportes', component: ReportesComponent },
      { path: 'existencias', component: ExistenciasComponent },
    ]
  }
];
