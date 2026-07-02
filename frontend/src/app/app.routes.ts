// src/app/app.routes.ts

import { Routes } from '@angular/router';
import { LoginComponent } from './pantalla-login/pantalla-login.component';
import { MainComponent } from './main/main.component';
import { PantallaVerTicketsComponent } from './pantalla-ver-tickets/pantalla-ver-tickets.component';
import { AdminPermisosComponent } from './admin-permisos/admin-permisos.component';
import { AuthGuard } from './guards/auth.guard';
import { AdminGuard } from './guards/admin.guard';
import { LayoutComponent } from './layout/layout.component';
import { AdminPanelComponent } from './admin-panel/admin-panel.component';
import { CrearTicketRefactorComponent } from './pantalla-crear-ticket/crear-ticket-refactor.component';
import { PmBitacorasMobileComponent } from './pm/pm-bitacoras-mobile/pm-bitacoras-mobile.component';
import { PmConsultaHistorialComponent } from './pm/pm-consulta-historial/pm-consulta-historial.component';
import { PmConfiguracionProgramacionComponent } from './pm/pm-configuracion-programacion/pm-configuracion-programacion.component';
import { PmCalendarioComponent } from './pm/pm-calendario/pm-calendario.component';
import { WarehouseHomeComponent } from './warehouse/warehouse-home.component';
import { TrackDashboardComponent } from './warehouse/track-dashboard/track-dashboard.component';
import { TrackKpiDesempenoComponent } from './warehouse/track-kpi-desempeno/track-kpi-desempeno.component';
import { TrackForecastComponent } from './warehouse/track-forecast/track-forecast.component';
import { TrackBranchHistoryComponent } from './warehouse/track-dashboard/track-branch-history/track-branch-history.component';
import { CommercialPromotionsComponent } from './warehouse/commercial-promotions/commercial-promotions.component';





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
        path: 'admin/permisos-observabilidad',
        canActivate: [AdminGuard],
        loadComponent: () =>
          import('./permissions-observability/permissions-observability.component')
            .then(m => m.PermissionsObservabilityComponent),
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
        path: 'planeacion/metas',
        loadComponent: () =>
          import('./planning/targets/planning-targets-home/planning-targets-home.component')
            .then((m) => m.PlanningTargetsHomeComponent),
      },
      {
        path: 'planeacion/metas/:batchId',
        loadComponent: () =>
          import('./planning/targets/planning-target-batch-detail/planning-target-batch-detail.component')
            .then((m) => m.PlanningTargetBatchDetailComponent),
      },
      {
        path: 'warehouse',
        component: WarehouseHomeComponent,
      },
      {
        path: 'warehouse/track',
        component: TrackDashboardComponent,
      },
      {
        path: 'warehouse/track/kpi-desempeno',
        component: TrackKpiDesempenoComponent,
      },
      {
        path: 'warehouse/track/forecast',
        component: TrackForecastComponent,
      },
      {
        path: 'warehouse/track-intelligence/regional',
        loadComponent: () =>
          import('./warehouse/track-intelligence-regional/track-intelligence-regional.component')
            .then(m => m.TrackIntelligenceRegionalComponent),
      },
      {
        path: 'warehouse/track/sucursal/:sucursalCanon',
        component: TrackBranchHistoryComponent,
      },
      {
        path: 'warehouse/comercial/promociones',
        component: CommercialPromotionsComponent,
      },
      {
        path: 'nube-corporativa',
        loadChildren: () =>
          import('./internal-documents/internal-documents.routes')
            .then(m => m.INTERNAL_DOCUMENTS_ROUTES),
      },
      {
        path: 'aperturas',
        loadChildren: () =>
          import('./openings/openings.routes').then((m) => m.OPENINGS_ROUTES),
      },
      {
        path: 'rpa/gasca-sms',
        loadComponent: () =>
          import('./rpa/gasca-sms/gasca-sms-requests.component')
            .then(m => m.GascaSmsRequestsComponent),
      },
    ],
  },

  { path: '**', redirectTo: 'login', pathMatch: 'full' },
];

