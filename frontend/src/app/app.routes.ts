// src/app/app.routes.ts

import { Routes } from '@angular/router';
import { LoginComponent } from './pantalla-login/pantalla-login.component';
import { MainComponent } from './main/main.component';
import { PantallaVerTicketsComponent } from './pantalla-ver-tickets/pantalla-ver-tickets.component';
import { AdminPermisosComponent } from './admin-permisos/admin-permisos.component';
import { AuthGuard } from './guards/auth.guard';
import { AdminGuard } from './guards/admin.guard';
import { LayoutComponent } from './layout/layout.component';
import { RegistrarAsistenciaComponent } from './registrar-asistencia/registrar-asistencia.component';
import { AdminPanelComponent } from './admin-panel/admin-panel.component';
import { CrearTicketRefactorComponent } from './pantalla-crear-ticket/crear-ticket-refactor.component';
import { PmBitacorasMobileComponent } from './pm/pm-bitacoras-mobile/pm-bitacoras-mobile.component';
import { PmConsultaHistorialComponent } from './pm/pm-consulta-historial/pm-consulta-historial.component';
import { PmConfiguracionProgramacionComponent } from './pm/pm-configuracion-programacion/pm-configuracion-programacion.component';
import { PmCalendarioComponent } from './pm/pm-calendario/pm-calendario.component';
import { WarehouseHomeComponent } from './warehouse/warehouse-home.component';


export const routes: Routes = [
  { path: '', redirectTo: 'login', pathMatch: 'full' },
  { path: 'login', component: LoginComponent },
  {
    path: 'admin',
    component: AdminPanelComponent,
  },
  {
    path: 'test-select',
    loadComponent: () => import('./prueba-select/prueba-select.component').then(m => m.PruebaSelectComponent)
  },

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
          { path: 'crear-ticket', component: CrearTicketRefactorComponent },
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
        path: 'pm/bitacoras-mobile',
        component: PmBitacorasMobileComponent,
      },
      {
        path: 'pm/escritorio-preventivo',
        loadComponent: () =>
          import('./pm/pm-escritorio-preventivo/pm-escritorio-preventivo.component')
            .then(m => m.PmEscritorioPreventComponent),
      },
      {
        path: 'pm/consulta-historial',
        component: PmConsultaHistorialComponent
      },
      {
        path: 'pm/configuracion-programacion',
        component: PmConfiguracionProgramacionComponent,
      },
      {
        path: 'pm/calendario',
        component: PmCalendarioComponent,
      },
      {
        path: 'catalogos',
        loadChildren: () => import('./inventario/catalogos/catalogos-routing.module').then(m => m.CatalogosRoutingModule)
      },
      {
        path: 'carga-masiva',
        loadComponent: () => import('./inventario/carga-masiva/pantalla-carga-masiva.component')
          .then(m => m.PantallaCargaMasivaComponent)
      },
      {
        path: 'admin-usuarios-sucursales',
        canActivate: [AdminGuard],
        loadComponent: () =>
          import('./pages/admin-usuarios-sucursales/admin-usuarios-sucursales.component')
            .then(m => m.AdminUsuariosSucursalesComponent),
      },
      {
        path: 'admin-usuarios-sucursales/:userId',
        canActivate: [AdminGuard],
        loadComponent: () =>
          import('./pages/admin-usuarios-sucursales/admin-usuarios-sucursales.component')
            .then(m => m.AdminUsuariosSucursalesComponent),
      },
      {
        path: 'asistencia/registrar',
        loadComponent: () => import('./registrar-asistencia/registrar-asistencia.component').then(m => m.RegistrarAsistenciaComponent)
      },
      {
        path: 'warehouse',
        component: WarehouseHomeComponent,
      },
    ],
  },

  { path: '**', redirectTo: 'login', pathMatch: 'full' },
];
