import { CommonModule } from '@angular/common';
import { Component, EventEmitter, Input, OnChanges, Output } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatCheckboxModule } from '@angular/material/checkbox';
import { MatDatepickerModule } from '@angular/material/datepicker';
import { MatDialogModule } from '@angular/material/dialog';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatNativeDateModule } from '@angular/material/core';
import { MatSelectModule } from '@angular/material/select';

import { InventarioService } from 'src/app/services/inventario.service';
import { MantenimientoEquiposService } from 'src/app/services/mantenimiento-equipos.service';
import {
  AsignarFechaPayload,
  CondicionOperativa,
  FallaMantenimientoDTO,
} from 'src/app/types/ticket';
import { mostrarAlertaToast } from 'src/app/utils/alertas';

@Component({
  selector: 'app-asignar-fecha-modal',
  standalone: true,
  templateUrl: './asignar-fecha-modal.component.html',
  styleUrls: ['./asignar-fecha-modal.component.css'],
  imports: [
    CommonModule,
    FormsModule,
    MatDialogModule,
    MatButtonModule,
    MatFormFieldModule,
    MatInputModule,
    MatDatepickerModule,
    MatNativeDateModule,
    MatCheckboxModule,
    MatSelectModule,
  ],
})
export class AsignarFechaModalComponent implements OnChanges {
  @Input() fechaSeleccionada: Date | null = null;
  @Input() puedeCapturarDiagnostico = false;

  @Input() set ticket(value: any | null) {
    this._ticket = value;

    if (value) {
      this.necesitaRefaccion = !!value.necesita_refaccion;
      this.descripcionRefaccion = value.descripcion_refaccion || '';
      this.familiaEquipoId = (
        value.inventario?.familia_equipo_id
        ?? value.familia_equipo_id
        ?? null
      );
      this.familiaEquipoNombre = (
        value.inventario?.familia_equipo?.nombre
        || value.familia_equipo?.nombre
        || value.familia
        || ''
      );
      this.fallaMantenimientoId = value.falla_mantenimiento_id ?? null;
      this.fallaMantenimientoNombre = (
        value.falla_mantenimiento?.nombre
        || value.falla
        || ''
      );
      this.condicionOperativa = value.condicion_operativa ?? null;
    } else {
      this.familiaEquipoId = null;
      this.familiaEquipoNombre = '';
      this.fallaMantenimientoId = null;
      this.fallaMantenimientoNombre = '';
      this.condicionOperativa = null;
    }

    this.fallas = [];
    this.aparatoFamiliaConsultado = null;
  }

  get ticket(): any | null {
    return this._ticket;
  }

  private _ticket: any | null = null;
  private aparatoFamiliaConsultado: number | null = null;
  private fallaMantenimientoNombre = '';

  @Output() onGuardar = new EventEmitter<AsignarFechaPayload>();
  @Output() onCancelar = new EventEmitter<void>();

  motivo = '';
  necesitaRefaccion = false;
  descripcionRefaccion = '';
  fallas: FallaMantenimientoDTO[] = [];
  familiaEquipoId: number | null = null;
  familiaEquipoNombre = '';
  fallaMantenimientoId: number | null = null;
  condicionOperativa: CondicionOperativa | null = null;
  cargandoCatalogos = false;

  readonly condicionesOperativas: Array<{
    value: CondicionOperativa;
    label: string;
  }> = [
    { value: 'TRABAJA', label: 'Trabaja' },
    { value: 'NO_TRABAJA', label: 'No trabaja' },
  ];

  readonly minDate: Date = (() => {
    const now = new Date();
    return new Date(now.getFullYear(), now.getMonth(), now.getDate());
  })();

  constructor(
    private readonly inventarioService: InventarioService,
    private readonly mantenimientoEquiposService: MantenimientoEquiposService,
  ) {}

  ngOnChanges(): void {
    if (!this.mostrarDiagnosticoEstructurado) {
      return;
    }

    if (this.familiaEquipoId) {
      this.cargarFallas(this.familiaEquipoId);
      return;
    }

    const aparatoId = Number(this._ticket?.aparato_id || 0);
    if (aparatoId > 0 && this.aparatoFamiliaConsultado !== aparatoId) {
      this.cargarFamiliaActual(aparatoId);
    }
  }

  get mostrarDiagnosticoEstructurado(): boolean {
    return this.puedeCapturarDiagnostico && Number(this._ticket?.aparato_id) > 0;
  }

  get aparatoSinFamilia(): boolean {
    return (
      this.mostrarDiagnosticoEstructurado
      && !this.cargandoCatalogos
      && !this.familiaEquipoId
    );
  }

  get guardarDeshabilitado(): boolean {
    return this.cargandoCatalogos || this.aparatoSinFamilia;
  }

  get mostrarRefaccionJefe(): boolean {
    const ticket = this._ticket;
    if (!ticket) return false;

    const departamento = this.getDepartamentoNormalizado();
    return departamento === 'mantenimiento' || departamento === 'sistemas';
  }

  guardar(): void {
    if (!this.fechaSeleccionada || !this.motivo.trim()) {
      mostrarAlertaToast(
        'Debes seleccionar una fecha y escribir un motivo.',
        'error',
      );
      return;
    }

    if (this.aparatoSinFamilia) {
      mostrarAlertaToast(
        'Este aparato no tiene una familia asignada. Clasifícalo primero desde Inventario.',
        'error',
      );
      return;
    }

    if (
      this.mostrarDiagnosticoEstructurado
      && (!this.fallaMantenimientoId || !this.condicionOperativa)
    ) {
      mostrarAlertaToast(
        'Selecciona familia, falla detectada y condición operativa.',
        'error',
      );
      return;
    }

    const payload: AsignarFechaPayload = {
      fecha: this.fechaSeleccionada,
      motivo: this.motivo.trim(),
    };

    if (this.mostrarRefaccionJefe) {
      payload.necesita_refaccion = !!this.necesitaRefaccion;
      payload.descripcion_refaccion = this.necesitaRefaccion
        ? (this.descripcionRefaccion || '')
        : '';
      payload.refaccion_definida_por_jefe = true;
    }

    if (this.mostrarDiagnosticoEstructurado) {
      payload.falla_mantenimiento_id = this.fallaMantenimientoId || undefined;
      payload.condicion_operativa = this.condicionOperativa || undefined;
    }

    this.onGuardar.emit(payload);
  }

  cancelar(): void {
    this.onCancelar.emit();
  }

  private cargarFamiliaActual(aparatoId: number): void {
    this.aparatoFamiliaConsultado = aparatoId;
    this.cargandoCatalogos = true;

    this.inventarioService.obtenerInventarioPorId(aparatoId).subscribe({
      next: (inventario) => {
        this.familiaEquipoId = inventario?.familia_equipo_id ?? null;
        this.familiaEquipoNombre = inventario?.familia_equipo?.nombre || '';
        this.cargandoCatalogos = false;

        if (this.familiaEquipoId) {
          this.cargarFallas(this.familiaEquipoId);
        }
      },
      error: () => {
        this.cargandoCatalogos = false;
        this.familiaEquipoId = null;
        this.familiaEquipoNombre = '';
        mostrarAlertaToast(
          'No se pudo consultar la familia actual del equipo.',
          'error',
        );
      },
    });
  }

  private cargarFallas(familiaEquipoId: number): void {
    this.cargandoCatalogos = true;
    const fallaPreseleccionada = this.fallaMantenimientoId;
    const fallaNombre = this.normalizar(this.fallaMantenimientoNombre);

    this.mantenimientoEquiposService.obtenerFallas(familiaEquipoId).subscribe({
      next: (fallas) => {
        this.fallas = fallas;
        this.cargandoCatalogos = false;

        if (
          fallaPreseleccionada
          && fallas.some((falla) => falla.id === fallaPreseleccionada)
        ) {
          this.fallaMantenimientoId = fallaPreseleccionada;
          return;
        }

        const fallaPorNombre = fallaNombre
          ? fallas.find(
              (falla) => this.normalizar(falla.nombre) === fallaNombre,
            )
          : undefined;
        this.fallaMantenimientoId = fallaPorNombre?.id ?? null;
      },
      error: () => {
        this.cargandoCatalogos = false;
        this.fallas = [];
        this.fallaMantenimientoId = null;
        mostrarAlertaToast(
          'No se pudieron cargar las fallas de la familia.',
          'error',
        );
      },
    });
  }

  private getDepartamentoNormalizado(): string {
    const ticket: any = this._ticket || {};
    const candidates = [
      ticket.departamento_nombre,
      ticket.departamento,
      ticket.jerarquia_clasificacion?.[0],
    ];

    for (const candidate of candidates) {
      if (candidate != null && candidate !== '') {
        return this.normalizar(candidate);
      }
    }

    return '';
  }

  private normalizar(value: any): string {
    return (value ?? '')
      .toString()
      .trim()
      .toLowerCase()
      .normalize('NFD')
      .replace(/[\u0300-\u036f]/g, '');
  }
}
