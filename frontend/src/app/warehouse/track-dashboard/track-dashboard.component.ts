//   frontend\src\app\warehouse\track-dashboard\track-dashboard.component.ts


import { Component } from '@angular/core';
import { CommonModule } from '@angular/common';

@Component({
  selector: 'app-track-dashboard',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './track-dashboard.component.html',
  styleUrls: ['./track-dashboard.component.css'],
})
export class TrackDashboardComponent {
  readonly pageTitle = 'Track diario';
  readonly pageSubtitle =
    'Genera snapshots manuales y consulta resultados del track dentro de Warehouse.';
}