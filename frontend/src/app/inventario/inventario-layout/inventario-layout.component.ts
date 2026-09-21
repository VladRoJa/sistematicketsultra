import { Component } from '@angular/core';
import { RouterModule } from '@angular/router';
import { MatIconModule } from '@angular/material/icon';

@Component({
  selector: 'app-inventario-layout',
  standalone: true,
  templateUrl: './inventario-layout.component.html',
  styleUrls: ['./inventario-layout.component.css'],
  imports: [
    RouterModule,
    MatIconModule,
  ],
})
export class InventarioLayoutComponent {}
