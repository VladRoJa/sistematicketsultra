import { CommonModule } from '@angular/common';
import { Component, Inject } from '@angular/core';
import { MAT_DIALOG_DATA, MatDialogModule, MatDialogRef } from '@angular/material/dialog';
import { MatIconModule } from '@angular/material/icon';
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
  imports: [CommonModule, MatDialogModule, MatIconModule],
  templateUrl: './dialogo-detalle-movimiento.component.html',
  styleUrls: ['./dialogo-detalle-movimiento.component.css'],
})
export class DialogoDetalleMovimientoComponent {
  readonly articulos: ArticuloDetalleMovimiento[];
  readonly etiquetaEstado: string;
  readonly usuarioRegistro: string;
  readonly nombreSucursal: string;
  readonly usuarioAnulacion: string;
  readonly etiquetaCantidadArticulos: string;

  constructor(
    @Inject(MAT_DIALOG_DATA) public data: DatosDialogoDetalleMovimiento,
    private dialogRef: MatDialogRef<DialogoDetalleMovimientoComponent>,
  ) {
    this.articulos = detallesMovimiento(data.movimiento, data.catalogo);
    this.etiquetaEstado = data.movimiento.anulado ? 'Anulado' : 'Activo';
    this.usuarioRegistro = this.etiquetaRegistro(
      data.movimiento.usuario, data.movimiento.usuario_id, 'Usuario'
    );
    this.nombreSucursal = this.etiquetaRegistro(
      data.movimiento.sucursal, data.movimiento.sucursal_id, 'Sucursal'
    );
    this.usuarioAnulacion = this.etiquetaRegistro(
      data.movimiento.usuario_anulacion,
      data.movimiento.anulado_por_usuario_id ?? undefined,
      'Usuario'
    );
    this.etiquetaCantidadArticulos = `${this.articulos.length} ${this.articulos.length === 1 ? 'artículo' : 'artículos'}`;
  }

  private etiquetaRegistro(valor: unknown, id: number | undefined, tipo: string): string {
    if (typeof valor === 'string' && valor.trim()) return valor.trim();
    return id != null ? `${tipo} #${id}` : '—';
  }

  cerrar(): void {
    this.dialogRef.close();
  }
}
