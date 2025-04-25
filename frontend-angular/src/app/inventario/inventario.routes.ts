import { Routes } from '@angular/router';
import { InventarioLayoutComponent } from './inventario-layout/inventario-layout.component';
import { ProductosComponent } from './productos/productos.component';
import { MovimientosComponent } from './movimientos/movimientos.component';
import { ReportesComponent } from './reportes/reportes.component';
import { ExistenciasComponent } from './existencias/existencias.component';

export const INVENTARIO_ROUTES: Routes = [
  {
    path: '',
    component: InventarioLayoutComponent,
    children: [
      { path: '', redirectTo: 'productos', pathMatch: 'full' },
      { path: 'productos', component: ProductosComponent },
      { path: 'movimientos', component: MovimientosComponent },
      { path: 'reportes', component: ReportesComponent },
      { path: 'existencias', component: ExistenciasComponent },
    ]
  }
];
