// frontend\src\app\pantalla-ver-tickets\modals\asignar-fecha-modal.component.ts
import { Component, EventEmitter, Input, OnChanges, Output } from '@angular/core';
import { CommonModule } from '@angular/common';
import { MatDialogModule } from '@angular/material/dialog';
import { MatButtonModule } from '@angular/material/button';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatDatepickerModule } from '@angular/material/datepicker';
import { MatNativeDateModule } from '@angular/material/core';
import { FormsModule } from '@angular/forms';
import { mostrarAlertaToast } from 'src/app/utils/alertas';
import { MatCheckboxModule } from '@angular/material/checkbox';
import { MatSelectModule } from '@angular/material/select';
import { MantenimientoEquiposService } from 'src/app/services/mantenimiento-equipos.service';
import {
  CondicionOperativa,
  FallaMantenimientoDTO,
} from 'src/app/types/ticket';

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
  ]
})
export class AsignarFechaModalComponent implements OnChanges {
  @Input() fechaSeleccionada: Date | null = null;
  @Input() puedeCapturarDiagnostico = false;

  // Recibe el ticket y hace prefill de refacción si ya existía
  @Input() set ticket(value: any | null) {
    this._ticket = value;
    console.debug('[modal] ticket recibido:', value);

    // Prefill si viene desde backend o tabla
    if (value) {
      this.necesitaRefaccion = !!value.necesita_refaccion;
      this.descripcionRefaccion = value.descripcion_refaccion || '';
      this.familiaEquipoId = value.inventario?.familia_equipo_id ?? null;
      this.familiaEquipoNombre = value.inventario?.familia_equipo?.nombre || '';
      this.fallaMantenimientoId = value.falla_mantenimiento_id ?? null;
      this.condicionOperativa = value.condicion_operativa ?? null;
    } else {
      this.familiaEquipoId = null;
      this.familiaEquipoNombre = '';
      this.fallaMantenimientoId = null;
      this.condicionOperativa = null;
    }
    this.fallas = [];
  }
  get ticket(): any | null { return this._ticket; }
  private _ticket: any | null = null;

  @Output() onGuardar = new EventEmitter<{
    fecha: Date;
    motivo: string;
    necesita_refaccion?: boolean;
    descripcion_refaccion?: string;
    refaccion_definida_por_jefe?: boolean;
    falla_mantenimiento_id?: number;
    condicion_operativa?: CondicionOperativa;
  }>();
  @Output() onCancelar = new EventEmitter<void>();

  motivo: string = '';

  // Estado local del mini-form
  necesitaRefaccion: boolean = false;
  descripcionRefaccion: string = '';
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

  constructor(
    private readonly mantenimientoEquiposService: MantenimientoEquiposService,
  ) {}

  ngOnChanges(): void {
    if (this.mostrarDiagnosticoEstructurado && this.familiaEquipoId) {
      this.cargarFallas(this.familiaEquipoId);
    }
  }

  get mostrarDiagnosticoEstructurado(): boolean {
    return this.puedeCapturarDiagnostico && Number(this._ticket?.aparato_id) > 0;
  }

  get aparatoSinFamilia(): boolean {
    return this.mostrarDiagnosticoEstructurado && !this.familiaEquipoId;
  }

  get guardarDeshabilitado(): boolean {
    return this.aparatoSinFamilia;
  }

  private cargarFallas(familiaEquipoId: number): void {
    this.cargandoCatalogos = true;
    const fallaPreseleccionada = this.fallaMantenimientoId;
    this.mantenimientoEquiposService.obtenerFallas(familiaEquipoId).subscribe({
      next: (fallas) => {
        this.fallas = fallas;
        this.cargandoCatalogos = false;
        this.fallaMantenimientoId = fallas.some(
          (falla) => falla.id === fallaPreseleccionada,
        )
          ? fallaPreseleccionada
          : null;
      },
      error: () => {
        this.cargandoCatalogos = false;
        this.fallas = [];
        this.fallaMantenimientoId = null;
        mostrarAlertaToast('No se pudieron cargar las fallas de la familia.', 'error');
      },
    });
  }

  private norm(v: any): string {
    return (v ?? '')
      .toString()
      .trim()
      .toLowerCase()
      .normalize('NFD')
      .replace(/[\u0300-\u036f]/g, '');
  }

  // ——— Detectores robustos (prioriza campos directos sobre jerarquía) ———
  private getDepNombreNorm(): string {
    const t: any = this._ticket || {};
    const candidates = [
      t?.departamento_nombre,   // ← 1º
      t?.departamento,          // ← 2º (por si llega texto crudo)
      t?.jerarquia_clasificacion?.[0], // ← 3º fallback
    ];
    for (const c of candidates) {
      if (c != null && c !== '') return this.norm(c);
    }
    return '';
  }

  private getCatNombreNorm(): string {
    const t: any = this._ticket || {};
    const candidates = [
      (typeof t?.categoria === 'object' ? t?.categoria?.nombre : t?.categoria), // ← 1º (string u objeto)
      t?.categoria_nivel_2,                                                    // ← 2º (variante)
      t?.jerarquia_clasificacion?.[1],                                         // ← 3º fallback
      (typeof t?.categoria_nivel2 === 'object' ? t?.categoria_nivel2?.nombre : t?.categoria_nivel2),
    ];
    for (const c of candidates) {
      if (c != null && c !== '') return this.norm(c);
    }
    return '';
  }

    public minDate: Date = (() => {
    const now = new Date();
    return new Date(now.getFullYear(), now.getMonth(), now.getDate());
  })();


  // Mostrar mini-form de refacción para TODO ticket de:
  // - Departamento: Mantenimiento
  // - Departamento: Sistemas
  get mostrarRefaccionJefe(): boolean {
    const t = this._ticket;
    if (!t) return false;

    const dep = this.getDepNombreNorm(); // ya normaliza a minúsculas y sin acentos

    const show = dep === 'mantenimiento' || dep === 'sistemas';

    console.debug('[modal] dep detectado (simple):', { dep, show, raw: t });

    return show;
  }



  guardar(): void {
    if (!this.fechaSeleccionada || !this.motivo.trim()) {
      mostrarAlertaToast('Debes seleccionar una fecha y escribir un motivo.', 'error');
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

    const payload: any = {
      fecha: this.fechaSeleccionada,
      motivo: this.motivo.trim(),
    };

    if (this.mostrarRefaccionJefe) {
      payload.necesita_refaccion = !!this.necesitaRefaccion;
      payload.descripcion_refaccion = this.necesitaRefaccion ? (this.descripcionRefaccion || '') : '';
      payload.refaccion_definida_por_jefe = true;
    }

    if (this.mostrarDiagnosticoEstructurado) {
      payload.falla_mantenimiento_id = this.fallaMantenimientoId;
      payload.condicion_operativa = this.condicionOperativa;
    }

    this.onGuardar.emit(payload);
  }

  cancelar(): void {
    this.onCancelar.emit();
  }
}
