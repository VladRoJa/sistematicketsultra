//frontend\src\app\warehouse\warehouse-home.component.ts


import { CommonModule } from '@angular/common';
import { Component, OnInit } from '@angular/core';
import { WarehouseAccessService } from '../services/warehouse-access.service';

@Component({
  selector: 'app-warehouse-home',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './warehouse-home.component.html',
  styleUrls: ['./warehouse-home.component.css']
})
export class WarehouseHomeComponent implements OnInit {
  loading = true;
  accessAllowed = false;
  errorMessage = '';

  constructor(private warehouseAccessService: WarehouseAccessService) {}

  ngOnInit(): void {
    this.loadAccess();
  }

  private loadAccess(): void {
    this.loading = true;
    this.errorMessage = '';

    this.warehouseAccessService.checkAccess().subscribe({
      next: (response) => {
        this.accessAllowed = response.allowed === true;
        this.loading = false;
      },
      error: (error) => {
        this.accessAllowed = false;
        this.loading = false;

        if (error.status === 403) {
          this.errorMessage = 'No autorizado para acceder a Warehouse.';
          return;
        }

        this.errorMessage = 'No se pudo validar el acceso a Warehouse.';
      }
    });
  }
}