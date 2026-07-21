import { Routes } from '@angular/router';

export const ROUTINE_CONTROL_ROUTES: Routes = [
  {
    path: '',
    loadComponent: () => import('./routine-control-dashboard/routine-control-dashboard.component')
      .then((m) => m.RoutineControlDashboardComponent),
  },
  {
    path: 'socios/:memberId',
    loadComponent: () => import('./routine-control-member-detail/routine-control-member-detail.component')
      .then((m) => m.RoutineControlMemberDetailComponent),
  },
  {
    path: 'corridas',
    loadComponent: () => import('./routine-control-runs/routine-control-runs.component')
      .then((m) => m.RoutineControlRunsComponent),
  },
];
