//app_routing.module.ts


import { NgModule } from '@angular/core';
import { RouterModule, Routes } from '@angular/router';
import { AuthGuard } from './guards/auth.guard';
import { LoginComponent } from './pantalla-login/pantalla-login.component';
import { MainComponent } from './main/main.component';
import { PantallaCrearTicketComponent } from './pantalla-crear-ticket/pantalla-crear-ticket.component';
import { PantallaVerTicketsComponent } from './pantalla-ver-tickets/pantalla-ver-tickets.component';

const routes: Routes = [
  { path: '', redirectTo: 'login', pathMatch: 'full' },
  { path: 'login', component: LoginComponent },
  { 
    path: 'main', component: MainComponent,
    children: [
      { path: '', redirectTo: 'ver-tickets', pathMatch: 'full' },
      { path: 'crear-ticket', component: PantallaCrearTicketComponent },
      { path: 'ver-tickets', component: PantallaVerTicketsComponent }
    ]
  },
  { path: '**', redirectTo: 'login', pathMatch: 'full' }
];

@NgModule({
  imports: [RouterModule.forRoot(routes)],
  exports: [RouterModule]
})
export class AppRoutingModule {}
