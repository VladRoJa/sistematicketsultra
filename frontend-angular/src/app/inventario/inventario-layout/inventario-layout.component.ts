// src/app/inventario/inventario-layout/inventario-layout.component.ts

import { Component } from '@angular/core';
import { RouterModule } from '@angular/router';
import { MatTabsModule } from '@angular/material/tabs';
import { MatCardModule } from '@angular/material/card';

@Component({
  selector: 'app-inventario-layout',
  standalone: true,
  templateUrl: './inventario-layout.component.html',
  styleUrls: ['./inventario-layout.component.css'],
  imports: [
    RouterModule,
    MatTabsModule,
    MatCardModule
  ],
})
export class InventarioLayoutComponent {}
