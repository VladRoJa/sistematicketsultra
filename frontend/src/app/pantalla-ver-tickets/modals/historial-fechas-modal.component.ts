// src/app/pantalla-ver-tickets/modals/historial-fechas-modal.component.ts

import { Component, Inject } from '@angular/core';
import { MAT_DIALOG_DATA, MatDialogModule, MatDialogRef } from '@angular/material/dialog';
import { Ticket } from '../pantalla-ver-tickets.component';
import { CommonModule } from '@angular/common';
import { MatButtonModule } from '@angular/material/button';
import { MatDividerModule } from '@angular/material/divider';
import { MatIconModule } from '@angular/material/icon';
import { MatTooltipModule } from '@angular/material/tooltip';

@Component({
  standalone: true,
  selector: 'app-historial-fechas-modal',
  templateUrl: './historial-fechas-modal.component.html',
  styleUrls: ['./historial-fechas-modal.component.scss'],
  imports: [
    CommonModule,
    MatDialogModule,
    MatButtonModule,
    MatDividerModule,
    MatIconModule,
    MatTooltipModule
  ]
})
export class HistorialFechasModalComponent {
  tz = 'America/Tijuana';
  fmtDate = 'dd/MM/yy';
  fmtDateTime = 'dd/MM/yyyy hh:mm a';

  constructor(
    @Inject(MAT_DIALOG_DATA) public data: Ticket,
    private dialogRef: MatDialogRef<HistorialFechasModalComponent>
  ) {}

  get historial(): any[] {
    return Array.isArray(this.data?.historial_fechas)
      ? this.data.historial_fechas
      : [];
  }

  get tieneHistorial(): boolean {
    return this.historial.length > 0;
  }

  getEstadoLabel(): string {
    return (this.data?.estado || '—')
      .toString()
      .replace(/_/g, ' ');
  }

  getEstadoClass(): string {
    const estado = (this.data?.estado || '')
      .toString()
      .trim()
      .toLowerCase()
      .replace(/\s+/g, '-')
      .replace(/_/g, '-');

    return `estado-${estado || 'sin-estado'}`;
  }

  getActivoNombre(): string {
    if (this.data?.inventario?.nombre) {
      return this.data.inventario.nombre;
    }

    if (this.data?.equipo) {
      return this.data.equipo;
    }

    return 'Sin activo asignado';
  }

  getCodigoInterno(): string | null {
    return this.data?.inventario?.codigo_interno || null;
  }

  getDepartamento(): string {
    const ticket = this.data as any;
    return ticket?.departamento?.nombre
      || ticket?.departamento
      || ticket?.departamento_nombre
      || '—';
  }

  getSucursal(): string {
    const ticket = this.data as any;
    return ticket?.sucursal_destino?.sucursal
      || ticket?.sucursal?.sucursal
      || ticket?.sucursal_nombre_destino
      || ticket?.sucursal_nombre
      || ticket?.sucursal
      || '—';
  }

  getCriticidad(): string {
    const ticket = this.data as any;
    const criticidad = ticket?.criticidad;

    return criticidad !== undefined && criticidad !== null
      ? String(criticidad)
      : '—';
  }

  getFechaSolucionItem(item: any): string | null {
    return item?.fecha || item?.fecha_solucion || null;
  }

  getFechaCambioItem(item: any): string | null {
    return item?.fechaCambio || item?.fecha_cambio || null;
  }

  getUsuarioItem(item: any): string {
    return item?.cambiadoPor
      || item?.usuario
      || item?.username
      || '—';
  }

  getMotivoItem(item: any): string {
    return (item?.motivo || item?.comentario || item?.razon || '')
      .toString()
      .trim();
  }

  debeMostrarTooltipMotivo(item: any): boolean {
    return this.getMotivoItem(item).length > 45;
  }

  esRechazoCierre(item: any): boolean {
    const tipo = (item?.tipo || '').toString().toLowerCase();
    const evento = (item?.evento || '').toString().toLowerCase();
    const estadoCierreNuevo = (item?.estadoCierreNuevo || '').toString().toLowerCase();
    const motivo = this.getMotivoItem(item).toLowerCase();

    return (
      tipo.includes('rechazo_cierre') ||
      evento.includes('rechazo_cierre') ||
      estadoCierreNuevo.includes('rechazado') ||
      motivo.includes('rechazado por el creador') ||
      motivo.includes('rechazo')
    );
  }

  getEventoLabel(item: any): string {
    if (this.esRechazoCierre(item)) {
      return 'Rechazo';
    }

    const tipo = (item?.tipo || item?.evento || '').toString().toLowerCase();

    if (tipo.includes('cierre')) {
      return 'Cierre';
    }

    return 'Cambio';
  }

  cerrar(): void {
    this.dialogRef.close();
  }
}