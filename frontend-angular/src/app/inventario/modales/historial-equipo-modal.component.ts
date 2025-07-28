//frontend-angular\src\app\inventario\modales\historial-equipo-modal.component.ts

import { Component, Inject } from '@angular/core';
import { MAT_DIALOG_DATA } from '@angular/material/dialog';

@Component({
  selector: 'app-historial-equipo-modal',
  templateUrl: './historial-equipo-modal.component.html',
})
export class HistorialEquipoModalComponent {
  movimientos = this.data.historial_movimientos || [];
  tickets = this.data.historial_tickets || [];

  columnasMovimientos = ['tipo', 'fecha', 'usuario', 'sucursal', 'observaciones'];
  columnasTickets = ['id', 'fecha_creacion', 'estado', 'descripcion'];

  constructor(@Inject(MAT_DIALOG_DATA) public data: any) {}
}


