// app.routes.ts


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

  // Rutas dentro del layout
  {
    path: '',
    component: LayoutComponent,
    canActivate: [AuthGuard], // Protege todo lo que está dentro con AuthGuard
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
        canActivate: [AdminGuard], // Solo admin
      },
    ],
  },

  { path: '**', redirectTo: 'login', pathMatch: 'full' },
];
