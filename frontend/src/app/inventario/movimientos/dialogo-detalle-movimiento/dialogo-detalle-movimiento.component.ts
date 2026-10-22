import { CommonModule } from '@angular/common';
import { Component, Inject } from '@angular/core';
import { MAT_DIALOG_DATA, MatDialogModule, MatDialogRef } from '@angular/material/dialog';
import {
  ArticuloDetalleMovimiento,
  MovimientoInventarioVista,
  ProductoCatalogoMovimiento,
  detallesMovimiento,
} from '../movimientos-vista.helper';

export interface DatosDialogoDetalleMovimiento {
  movimiento: MovimientoInventarioVista;
  catalogo: ProductoCatalogoMovimiento[];
}

@Component({
  selector: 'app-dialogo-detalle-movimiento',
  standalone: true,
  imports: [CommonModule, MatDialogModule],
  templateUrl: './dialogo-detalle-movimiento.component.html',
  styleUrls: ['./dialogo-detalle-movimiento.component.css'],
})
export class DialogoDetalleMovimientoComponent {
  readonly articulos: ArticuloDetalleMovimiento[];

  constructor(
    @Inject(MAT_DIALOG_DATA) public data: DatosDialogoDetalleMovimiento,
    private dialogRef: MatDialogRef<DialogoDetalleMovimientoComponent>,
  ) {
    this.articulos = detallesMovimiento(data.movimiento, data.catalogo);
  }

  cerrar(): void {
    this.dialogRef.close();
  }
}
