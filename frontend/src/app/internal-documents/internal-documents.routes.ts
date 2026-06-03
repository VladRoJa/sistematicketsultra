// frontend/src/app/internal-documents/internal-documents.routes.ts

import { Routes } from '@angular/router';

export const INTERNAL_DOCUMENTS_ROUTES: Routes = [
  {
    path: '',
    loadComponent: () =>
      import('./pages/internal-documents-home/internal-documents-home.component')
        .then((m) => m.InternalDocumentsHomeComponent),
  },
];