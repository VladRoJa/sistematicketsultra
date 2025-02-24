//app.routes.ts

import { Routes } from '@angular/router';
import { LoginComponent } from './pantalla-login/pantalla-login.component';
import { MainComponent } from './main/main.component';
import { PantallaCrearTicketComponent } from './pantalla-crear-ticket/pantalla-crear-ticket.component';
import { PantallaVerTicketsComponent } from './pantalla-ver-tickets/pantalla-ver-tickets.component';

export const routes: Routes = [
  { path: '', redirectTo: 'login', pathMatch: 'full' }, // Sin '/'
  { path: 'login', component: LoginComponent },
  { 
    path: 'main', component: MainComponent,
    children: [
      { path: '', redirectTo: 'ver-tickets', pathMatch: 'full' }, // Carga 'ver-tickets' por defecto
      { path: 'crear-ticket', component: PantallaCrearTicketComponent },
      { path: 'ver-tickets', component: PantallaVerTicketsComponent }
    ]
  },
  { path: '**', redirectTo: 'login', pathMatch: 'full' } // Redirección a login si la ruta no existe
];
