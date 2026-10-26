import { Component, Inject, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { MatCheckboxModule, MatCheckboxChange } from '@angular/material/checkbox';
import { MatProgressBarModule } from '@angular/material/progress-bar';
import { MAT_DIALOG_DATA, MatDialogModule, MatDialogRef } from '@angular/material/dialog';
import { MatIconModule } from '@angular/material/icon';
import { TicketService, AparatoTapizadoRecepcion, AvanceTapizado, DetalleRecepcionTapizado } from '../../services/ticket.service';
import { Ticket } from '../pantalla-ver-tickets.component';

@Component({
  standalone: true,
  selector: 'app-tapizado-recepcion-modal',
  templateUrl: './tapizado-recepcion-modal.component.html',
  styleUrls: ['./tapizado-recepcion-modal.component.scss'],
  imports: [CommonModule, FormsModule, MatCheckboxModule, MatProgressBarModule, MatDialogModule, MatIconModule],
})
export class TapizadoRecepcionModalComponent implements OnInit {
  readonly tz = 'America/Tijuana';
  readonly fmtDateTime = 'dd/MM/yyyy hh:mm a';

  cargandoRecepcion = false;
  guardandoRecepciones = false;
  puedeEditarRecepcion = false;
  errorRecepcion = '';
  huboCambioRecepcion = false;

  confirmarDescarteVisible = false;
  motivosReversion: Record<number, string> = {};
  aparatosTapizado: AparatoTapizadoRecepcion[] = [];
  avanceTapizado: AvanceTapizado | null = null;

  // El check es un borrador local; el servidor conserva los datos oficiales.
  private borradorRecepciones = new Map<number, boolean>();
  cambiosPendientes: Array<{
    inventario_id: number;
    recibido: boolean;
    estado_anterior: boolean;
    motivo?: string;
  }> = [];

  get esTapizado(): boolean {
    return this.data?.tipo_trabajo === 'TAPIZADO';
  }

  get cantidadAltas(): number {
    return this.cambiosPendientes.filter(cambio => cambio.recibido).length;
  }

  get cantidadReversiones(): number {
    return this.cambiosPendientes.filter(cambio => !cambio.recibido).length;
  }

  get cambiosValidos(): boolean {
    return this.cambiosPendientes.length > 0 && this.cambiosPendientes.every(cambio =>
      cambio.recibido || (this.motivosReversion[cambio.inventario_id] || '').trim().length > 0
    );
  }

  constructor(
    @Inject(MAT_DIALOG_DATA) public data: Ticket,
    private dialogRef: MatDialogRef<TapizadoRecepcionModalComponent>,
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
    this.recargarRecepciones();
  }

  private recargarRecepciones(): void {
    this.cargandoRecepcion = true;
    this.puedeEditarRecepcion = false;
    this.ticketService.consultarRecepcionTapizado(this.data.id).subscribe({
      next: result => {
        this.actualizarDatosRecepcion(result);
        this.puedeEditarRecepcion = result.puede_editar === true;
        this.cargandoRecepcion = false;
        this.errorRecepcion = '';
      },
      error: err => {
        this.cargandoRecepcion = false;
        this.errorRecepcion = err?.error?.mensaje || 'No se pudo consultar las recepciones.';
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
    this.restablecerBorrador();
  }

  private restablecerBorrador(): void {
    this.borradorRecepciones = new Map(
      this.aparatosTapizado.map(aparato => [aparato.id, aparato.recibido])
    );
    this.motivosReversion = {};
    this.cambiosPendientes = [];

    this.confirmarDescarteVisible = false;
    this.dialogRef.disableClose = false;
  }

  estaMarcado(aparato: AparatoTapizadoRecepcion): boolean {
    return this.borradorRecepciones.get(aparato.id) ?? aparato.recibido;
  }

  cambioPendiente(aparato: AparatoTapizadoRecepcion): boolean {
    return this.estaMarcado(aparato) !== aparato.recibido;
  }

  cambiarRecepcion(aparato: AparatoTapizadoRecepcion, event: MatCheckboxChange): void {
    if (!this.puedeEditarRecepcion || this.cargandoRecepcion || this.guardandoRecepciones) {
      event.source.checked = this.estaMarcado(aparato);
      return;
    }
    this.borradorRecepciones.set(aparato.id, event.checked);
    this.recalcularCambios();
  }

  private recalcularCambios(): void {
    this.cambiosPendientes = this.aparatosTapizado
      .filter(aparato => this.cambioPendiente(aparato))
      .map(aparato => ({
        inventario_id: aparato.id,
        estado_anterior: aparato.recibido,
        recibido: this.estaMarcado(aparato),
      }));

    this.confirmarDescarteVisible = false;
    this.dialogRef.disableClose = this.cambiosPendientes.length > 0;
  }

  descartarSeleccion(): void {
    if (this.guardandoRecepciones) return;
    this.restablecerBorrador();
    this.errorRecepcion = '';
  }

  guardarCambios(): void {
    // Único momento en que el borrador llega al backend.
    if (!this.puedeEditarRecepcion || !this.cambiosPendientes.length ||
        !this.cambiosValidos || this.cargandoRecepcion || this.guardandoRecepciones) return;
    const cambios = this.cambiosPendientes.map(cambio => ({
      ...cambio,
      motivo: cambio.recibido
        ? undefined
        : this.motivosReversion[cambio.inventario_id]?.trim(),
    }));
    this.guardandoRecepciones = true;
    this.errorRecepcion = '';
    this.ticketService.guardarRecepcionesTapizado(this.data.id, cambios).subscribe({
      next: result => {
        this.guardandoRecepciones = false;
        this.actualizarDatosRecepcion(result);
        this.huboCambioRecepcion = true;
      },
      error: err => {
        this.guardandoRecepciones = false;

        this.errorRecepcion = err?.error?.mensaje || 'No se guardó ningún cambio. Revisa e intenta nuevamente.';
        // Mantener la selección para que el usuario pueda revisar/reintentar.
      },
    });
  }

  cancelarDescarte(): void {
    this.confirmarDescarteVisible = false;
  }

  descartarYCerrar(): void {
    if (this.guardandoRecepciones) return;
    this.descartarSeleccion();
    this.dialogRef.close(this.huboCambioRecepcion);
  }

  cerrar(): void {
    if (this.guardandoRecepciones) return;
    if (this.cambiosPendientes.length > 0) {
      this.confirmarDescarteVisible = true;
      return;
    }
    this.dialogRef.close(this.huboCambioRecepcion);
  }
}
