// src/app/pantalla-ver-tickets/modals/historial-fechas-modal.component.ts

import { Component, Inject, OnInit } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatCheckboxModule, MatCheckboxChange } from '@angular/material/checkbox';
import { MatProgressBarModule } from '@angular/material/progress-bar';
import { TicketService, AparatoTapizadoRecepcion, AvanceTapizado, DetalleRecepcionTapizado } from '../../services/ticket.service';
import { MAT_DIALOG_DATA, MatDialogModule, MatDialogRef } from '@angular/material/dialog';
import { Ticket } from '../pantalla-ver-tickets.component';
import { CommonModule } from '@angular/common';
import { MatButtonModule } from '@angular/material/button';
import { MatDividerModule } from '@angular/material/divider';
import { MatIconModule } from '@angular/material/icon';
import { MatTooltipModule } from '@angular/material/tooltip';
import {
  CambioResponsableHistorial,
  esEventoCoordinacion,
  esEventoReasignacion,
  obtenerCambioResponsableHistorial,
} from './historial-fechas-display';

@Component({
  standalone: true,
  selector: 'app-historial-fechas-modal',
  templateUrl: './historial-fechas-modal.component.html',
  styleUrls: ['./historial-fechas-modal.component.scss'],
  imports: [
    CommonModule,
    FormsModule,
    MatCheckboxModule,
    MatProgressBarModule,
    MatDialogModule,
    MatButtonModule,
    MatDividerModule,
    MatIconModule,
    MatTooltipModule
  ]
})
export class HistorialFechasModalComponent implements OnInit {
  tz = 'America/Tijuana';
  fmtDate = 'dd/MM/yy';
  fmtDateTime = 'dd/MM/yyyy hh:mm a';

  cargandoRecepcion = false;
  guardandoAparatoId: number | null = null;
  puedeEditarRecepcion = false;
  errorRecepcion = '';
  huboCambioRecepcion = false;
  revertirAparatoId: number | null = null;
  motivoReversion = '';
  aparatosTapizado: AparatoTapizadoRecepcion[] = [];
  avanceTapizado: AvanceTapizado | null = null;

  get esTapizado(): boolean {
    return this.data?.tipo_trabajo === 'TAPIZADO';
  }

  constructor(
    @Inject(MAT_DIALOG_DATA) public data: Ticket,
    private dialogRef: MatDialogRef<HistorialFechasModalComponent>,
    private ticketService: TicketService,
  ) {}

  ngOnInit(): void {
    if (!this.esTapizado) return;
    this.aparatosTapizado = (this.data.aparatos || []).map(ap => ({
      id: ap.id,
      nombre: ap.nombre,
      codigo_interno: ap.codigo_interno,
      familia_equipo_id: ap.familia_equipo_id,
      recibido: ap.recibido === true,
      recibido_en: ap.recibido_en ?? null,
      recibido_por: ap.recibido_por ?? null,
    }));
    this.avanceTapizado = this.data.avance_tapizado || null;
    this.cargandoRecepcion = true;
    this.ticketService.consultarRecepcionTapizado(this.data.id).subscribe({
      next: result => {
        this.actualizarDatosRecepcion(result);
        this.puedeEditarRecepcion = result.puede_editar === true;
        this.cargandoRecepcion = false;
      },
      error: err => {
        this.cargandoRecepcion = false;
        this.errorRecepcion = err?.error?.mensaje || 'No fue posible actualizar la información de Tapizado.';
      },
    });
  }

  private actualizarDatosRecepcion(result: DetalleRecepcionTapizado): void {
    this.aparatosTapizado = result.aparatos || [];
    this.avanceTapizado = result.avance || null;
    this.data.aparatos = this.aparatosTapizado;
    this.data.avance_tapizado = this.avanceTapizado;
    if (result.historial_fechas) {
      this.data.historial_fechas = result.historial_fechas as any;
    }
  }

  cambiarRecepcion(aparato: AparatoTapizadoRecepcion, event: MatCheckboxChange): void {
    // Sólo la respuesta del servidor puede modificar un checkbox.
    event.source.checked = aparato.recibido;
    if (!this.puedeEditarRecepcion || this.guardandoAparatoId !== null) return;
    if (aparato.recibido && !event.checked) {
      this.revertirAparatoId = aparato.id;
      this.motivoReversion = '';
      return;
    }
    if (!aparato.recibido && event.checked) {
      this.guardarRecepcion(aparato, true);
    }
  }

  cancelarReversion(): void {
    this.revertirAparatoId = null;
    this.motivoReversion = '';
  }

  confirmarReversion(aparato: AparatoTapizadoRecepcion): void {
    if (this.motivoReversion.trim().length === 0) {
      this.errorRecepcion = 'Escribe el motivo para revertir la recepción.';
      return;
    }
    this.guardarRecepcion(aparato, false, this.motivoReversion.trim());
  }

  private guardarRecepcion(aparato: AparatoTapizadoRecepcion, recibido: boolean, motivo?: string): void {
    this.guardandoAparatoId = aparato.id;
    this.errorRecepcion = '';
    this.ticketService.registrarRecepcionTapizado(this.data.id, aparato.id, recibido, motivo).subscribe({
      next: result => {
        this.actualizarDatosRecepcion(result);
        this.huboCambioRecepcion = true;
        this.guardandoAparatoId = null;
        this.cancelarReversion();
      },
      error: err => {
        this.guardandoAparatoId = null;
        this.errorRecepcion = err?.error?.mensaje || 'No se pudo guardar la recepción.';
      },
    });
  }

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
    if (this.esTapizado) {
      return `Tapizado · ${this.avanceTapizado?.total ?? this.data.aparatos_ids?.length ?? 0} aparatos`;
    }
    if (this.data?.inventario?.nombre) {
      return this.data.inventario.nombre;
    }

    if (this.data?.equipo) {
      return this.data.equipo;
    }

    return 'Sin activo asignado';
  }

  getCodigoInterno(): string | null {
    if (this.esTapizado) return null;
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
    const motivo = (item?.motivo || item?.comentario || item?.razon || '')
      .toString().trim();
    if (item?.tipo === 'tapizado_recepcion_aparato_v1') {
      const codigo = (item?.codigo_interno || item?.aparato_nombre || '').toString().trim();
      return codigo ? `${codigo} · ${motivo}` : motivo;
    }
    return motivo;
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

  esReasignacion(item: any): boolean {
    return esEventoReasignacion(item);
  }

  esCoordinacion(item: any): boolean {
    return esEventoCoordinacion(item);
  }

  getCambioResponsableItem(item: any): CambioResponsableHistorial | null {
    return obtenerCambioResponsableHistorial(item);
  }

  getEventoLabel(item: any): string {
    if (this.esRechazoCierre(item)) {
      return 'Rechazo';
    }

    if (item?.tipo === 'tapizado_recepcion_aparato_v1') {
      return item.recibido_nuevo ? 'Recibido' : 'Recepción revertida';
    }
    if (item?.tipo === 'maintenance_conformity_accepted_v1') {
      return 'Conformidad aceptada';
    }

    if (this.esReasignacion(item)) return 'Reasignación';
    if (this.esCoordinacion(item)) return 'Coordinación';

    const tipo = (item?.tipo || item?.evento || '').toString().toLowerCase();

    if (tipo.includes('cierre')) {
      return 'Cierre';
    }

    return 'Cambio';
  }

  cerrar(): void {
    this.dialogRef.close(this.huboCambioRecepcion);
  }
}