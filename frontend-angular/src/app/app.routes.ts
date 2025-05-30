// src/app/app.routes.ts

import { Routes } from '@angular/router';
import { LoginComponent } from './pantalla-login/pantalla-login.component';
import { MainComponent } from './main/main.component';
import { PantallaCrearTicketComponent } from './pantalla-crear-ticket/pantalla-crear-ticket.component';
import { PantallaVerTicketsComponent } from './pantalla-ver-tickets/pantalla-ver-tickets.component';
import { AdminPermisosComponent } from './admin-permisos/admin-permisos.component';
import { AuthGuard } from './guards/auth.guard';
import { AdminGuard } from './guards/admin.guard';
import { LayoutComponent } from './layout/layout.component';

export const routes: Routes = [
  { path: '', redirectTo: 'login', pathMatch: 'full' },
  { path: 'login', component: LoginComponent },

  {
    path: '',
    component: LayoutComponent,
    canActivate: [AuthGuard],
    children: [
      {
        path: 'main',
        component: MainComponent,
        children: [
          { path: '', redirectTo: 'ver-tickets', pathMatch: 'full' },
          { path: 'crear-ticket', component: PantallaCrearTicketComponent },
          { path: 'ver-tickets', component: PantallaVerTicketsComponent },
        ],
      },
      {
        path: 'admin-permisos',
        component: AdminPermisosComponent,
        canActivate: [AdminGuard],
      },
      {
        path: 'inventario',
        canActivate: [AuthGuard],
        loadChildren: () => import('./inventario/inventario.routes').then(m => m.INVENTARIO_ROUTES)
      },
      {
        path: 'carga-masiva',
        loadComponent: () => import('./inventario/carga-masiva/pantalla-carga-masiva.component')
          .then(m => m.PantallaCargaMasivaComponent)
      }
    ],
  },

  { path: '**', redirectTo: 'login', pathMatch: 'full' },
];
