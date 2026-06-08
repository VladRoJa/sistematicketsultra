//   frontend/src/app/openings/openings.routes.ts


import { Routes } from '@angular/router';

export const OPENINGS_ROUTES: Routes = [
  {
    path: '',
    loadComponent: () =>
      import('./pages/openings-list/openings-list.component')
        .then((m) => m.OpeningsListComponent),
  },
  {
    path: ':openingId',
    loadComponent: () =>
      import('./pages/opening-detail/opening-detail.component')
        .then((m) => m.OpeningDetailComponent),
  },
];