// frontend\src\app\pm\pm-consulta-historial\pm-consulta-historial.component.ts


import { Component, OnInit, inject, ViewChild, ElementRef, ChangeDetectorRef } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule, FormControl, ReactiveFormsModule } from '@angular/forms';
import { Observable } from 'rxjs';
import { map, startWith } from 'rxjs/operators';
import { SessionService } from '../../core/auth/session.service';

import { MatAutocompleteModule } from '@angular/material/autocomplete';
import { MatCardModule } from '@angular/material/card';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatButtonModule } from '@angular/material/button';
import { MatTableModule } from '@angular/material/table';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatSelectModule } from '@angular/material/select';

import { PmPreventivoService } from '../../services/pm-preventivo.service';
import {
  PmBitacoraDetalle,
  PmBitacoraResumen,
  SucursalOption,
} from '../../models/pm-preventivo.model';

@Component({
  selector: 'app-pm-consulta-historial',
  standalone: true,
  imports: [
    CommonModule,
    FormsModule,
    ReactiveFormsModule,
    MatAutocompleteModule,
    MatCardModule,
    MatFormFieldModule,
    MatInputModule,
    MatButtonModule,
    MatTableModule,
    MatSnackBarModule,
    MatProgressSpinnerModule,
    MatSelectModule
  ],
  templateUrl: './pm-consulta-historial.component.html',
  styleUrls: ['./pm-consulta-historial.component.css'],
})
export class PmConsultaHistorialComponent implements OnInit {
  private pmService = inject(PmPreventivoService);
  private snack = inject(MatSnackBar);
  private session = inject(SessionService);
  private cdr = inject(ChangeDetectorRef);

@ViewChild('detalleBitacoraCard', { read: ElementRef })
detalleBitacoraCard?: ElementRef<HTMLElement>;

  loading = false;
  sucursalesLoading = false;

  sucursalesList: SucursalOption[] = [];
  filteredSucursales$!: Observable<SucursalOption[]>;
  sucursalCtrl = new FormControl<string | SucursalOption>('');
  selectedSucursalId: number | null = null;

  fechaDesde = '';
  fechaHasta = '';

  bitacoras: PmBitacoraResumen[] = [];
  detalleBitacoraPm: PmBitacoraDetalle | null = null;
  detalleBitacoraLoading = false;
  detalleBitacoraEquipoLabel = '';
  bitacoraSeleccionadaId: number | null = null;

  mostrarRechazoPm = false;
  motivoRechazoPm = '';

  readonly displayedColumns = [
    'fecha',
    'equipo',
    'sucursal',
    'resultado',
    'estado_validacion',
  ];

  subcategoriaSeleccionada = 'TODAS';

  readonly subcategoriasDisponibles = [
      { value: 'TODAS', label: 'Ver todo' },
      { value: 'spinning', label: 'Spinning' },
      { value: 'cardio', label: 'Cardio' },
      { value: 'selectorizado', label: 'Selectorizado' },
      { value: 'peso libre', label: 'Peso libre' },
  ];

  ngOnInit(): void {
    this.cargarSucursales();

    this.filteredSucursales$ = this.sucursalCtrl.valueChanges.pipe(
      startWith(''),
      map((value) => {
        const term = (typeof value === 'string' ? value : value?.sucursal || '')
          .toLowerCase()
          .trim();

        if (!term) {
          return this.sucursalesList;
        }

        return this.sucursalesList.filter((s) =>
          s.sucursal.toLowerCase().includes(term)
        );
      })
    );
  }

  private cargarSucursales(): void {
    this.sucursalesLoading = true;

    this.pmService.getSucursalesPermitidas().subscribe({
      next: (rows) => {
        this.sucursalesList = rows || [];
        this.sucursalesLoading = false;

        if (this.sucursalesList.length === 1) {
          this.selectedSucursalId = this.sucursalesList[0].sucursal_id;
          this.sucursalCtrl.setValue(this.sucursalesList[0], { emitEvent: false });
        }
      },
      error: () => {
        this.sucursalesLoading = false;
        this.snack.open('No se pudieron cargar sucursales', 'OK', {
          duration: 3000,
        });
      },
    });
  }

  onSucursalSelected(sucursal: SucursalOption): void {
    this.selectedSucursalId = sucursal.sucursal_id;
    this.sucursalCtrl.setValue(sucursal, { emitEvent: false });
  }

  sucursalDisplay(value: SucursalOption | string | null): string {
    if (!value) return '';
    return typeof value === 'string' ? value : value.sucursal;
  }

  cargarBitacoras(): void {
    this.loading = true;
    this.bitacoras = [];
    this.cerrarDetalleBitacora();

    this.pmService
      .listarBitacoras(
        this.selectedSucursalId,
        this.fechaDesde || null,
        this.fechaHasta || null,
        this.subcategoriaSeleccionada
      )
      .subscribe({
        next: (rows) => {
          this.bitacoras = rows || [];
          this.loading = false;
        },
        error: (err) => {
          this.loading = false;
          const msg =
            err?.error?.detail ||
            err?.error?.message ||
            'No se pudieron cargar las bitácoras PM';
          this.snack.open(msg, 'OK', { duration: 3500 });
        },
      });
  }

  equipoLabel(row: PmBitacoraResumen): string {
    return [row.codigo_interno, row.nombre].filter(Boolean).join(' — ');
  }

  verDetalleBitacora(row: PmBitacoraResumen): void {
    this.detalleBitacoraLoading = true;
    this.detalleBitacoraPm = null;
    this.detalleBitacoraEquipoLabel = this.equipoLabel(row);
    this.mostrarRechazoPm = false;
    this.motivoRechazoPm = '';

    this.pmService.getBitacoraDetalle(row.id).subscribe({
      next: (detalle) => {
        this.detalleBitacoraPm = detalle;
        console.log('detalleBitacoraPm', this.detalleBitacoraPm);
        this.bitacoraSeleccionadaId = row.id;
        this.detalleBitacoraLoading = false;
        this.cdr.detectChanges();
        this.scrollAlDetalleBitacora();
      },
      error: (err) => {
        this.detalleBitacoraLoading = false;
        const msg =
          err?.error?.detail ||
          err?.error?.message ||
          'No se pudo cargar el detalle de la bitácora PM';
        this.snack.open(msg, 'OK', { duration: 3500 });
      },
    });
  }

  cerrarDetalleBitacora(): void {
    this.detalleBitacoraPm = null;
    this.detalleBitacoraLoading = false;
    this.detalleBitacoraEquipoLabel = '';
    this.bitacoraSeleccionadaId = null;
  }

  toggleDetalleBitacora(row: PmBitacoraResumen): void {
    if (this.bitacoraSeleccionadaId === row.id) {
      this.cerrarDetalleBitacora();
      return;
    }

    this.verDetalleBitacora(row);
  }

  formatearTipoMantenimiento(tipo: string | null | undefined): string {
  if (!tipo) return 'Sin tipo';

  const labels: Record<string, string> = {
    CORRECTIVO: 'Correctivo',
    PREVENTIVO: 'Preventivo',
    ESTETICO: 'Estético',
    MEJORA: 'Mejora',
  };

  return labels[tipo] || tipo;
}

formatearResultadoBitacora(resultado: string | null | undefined): string {
  if (!resultado) return 'Sin resultado';

  const labels: Record<string, string> = {
    OK: 'Ok',
    FALLA: 'Falla',
    OBS: 'Observación',
  };

  return labels[resultado] || resultado;
}

obtenerNombreSucursalDetalle(): string {
  const sucursalId = this.detalleBitacoraPm?.sucursal_id;

  if (!sucursalId) {
    return 'Sin sucursal';
  }

  const sucursal = this.sucursalesList.find(
    (s) => s.sucursal_id === sucursalId
  );

  return sucursal?.sucursal || 'Sin sucursal';
}

formatearFechaDetalle(fecha: string | null | undefined): string {
  if (!fecha) return 'Sin fecha';

  const partes = fecha.split('-');
  if (partes.length !== 3) return fecha;

  const [yyyy, mm, dd] = partes;
  return `${dd}/${mm}/${yyyy}`;
}

puedeValidarPm(): boolean {
  const user = this.session.getUser();
  const rol = (user?.rol || '').toString().trim().toUpperCase();

  return ['GERENTE', 'GERENTE_REGIONAL', 'MANTENIMIENTO'].includes(rol);
}

validarBitacoraPm(): void {
  const bitacoraId = this.detalleBitacoraPm?.id;

  if (!bitacoraId) {
    this.snack.open('No hay bitácora seleccionada para validar', 'OK', {
      duration: 3000,
    });
    return;
  }

  this.pmService
    .crearValidacionPm({
      bitacora_pm_id: bitacoraId,
      decision: 'VALIDADO',
    })
    .subscribe({
      next: () => {
        this.snack.open('Bitácora validada correctamente', 'OK', {
          duration: 3000,
        });

        this.cargarBitacoras();
      },
      error: (err) => {
        const msg =
          err?.error?.detail ||
          err?.error?.message ||
          'No se pudo validar la bitácora PM';

        this.snack.open(msg, 'OK', { duration: 3500 });
      },
    });
}

private scrollAlDetalleBitacora(): void {
  setTimeout(() => {
    const elemento = this.detalleBitacoraCard?.nativeElement;
    if (!elemento) {
      console.log('scroll detalle -> sin elemento');
      return;
    }

    const rectTop = elemento.getBoundingClientRect().top;
    const top = rectTop + window.scrollY - 16;

    console.log('scroll detalle -> antes', {
      rectTop,
      windowScrollY: window.scrollY,
      targetTop: top,
    });

    window.scrollTo({
      top,
      behavior: 'smooth',
    });

    setTimeout(() => {
      console.log('scroll detalle -> despues', {
        windowScrollY: window.scrollY,
      });
    }, 300);
  }, 0);
}


rechazarBitacoraPm(): void {
  const bitacoraId = this.detalleBitacoraPm?.id;
  const motivo = this.motivoRechazoPm.trim();

  if (!bitacoraId) {
    this.snack.open('No hay bitácora seleccionada para rechazar', 'OK', {
      duration: 3000,
    });
    return;
  }

  if (!motivo) {
    this.snack.open('Debes capturar un motivo de rechazo', 'OK', {
      duration: 3000,
    });
    return;
  }

  this.pmService
    .crearValidacionPm({
      bitacora_pm_id: bitacoraId,
      decision: 'RECHAZADO',
      motivo,
    })
    .subscribe({
      next: () => {
        this.snack.open('Bitácora rechazada correctamente', 'OK', {
          duration: 3000,
        });

        this.mostrarRechazoPm = false;
        this.motivoRechazoPm = '';

        this.cargarBitacoras();
      },
      error: (err) => {
        const msg =
          err?.error?.detail ||
          err?.error?.message ||
          'No se pudo rechazar la bitácora PM';

        this.snack.open(msg, 'OK', { duration: 3500 });
      },
    });
}

textoBotonRechazoPm(): string {
  if (this.mostrarRechazoPm && this.motivoRechazoPm.trim()) {
    return 'Confirmar rechazo';
  }

  return 'Rechazar';
}

manejarBotonRechazoPm(): void {
  if (!this.mostrarRechazoPm) {
    this.mostrarRechazoPm = true;
    return;
  }

  if (!this.motivoRechazoPm.trim()) {
    this.snack.open('Debes capturar un motivo de rechazo', 'OK', {
      duration: 3000,
    });
    return;
  }

  this.rechazarBitacoraPm();
}

formatearFechaValidacion(fechaIso: string | null | undefined): string {
  if (!fechaIso) return 'Sin fecha';

  const fecha = new Date(fechaIso);

  if (Number.isNaN(fecha.getTime())) {
    return fechaIso;
  }

  const dd = String(fecha.getDate()).padStart(2, '0');
  const mm = String(fecha.getMonth() + 1).padStart(2, '0');
  const yyyy = fecha.getFullYear();
  const hh = String(fecha.getHours()).padStart(2, '0');
  const min = String(fecha.getMinutes()).padStart(2, '0');

  return `${dd}/${mm}/${yyyy} ${hh}:${min}`;
}

formatearEstadoValidacion(estado: string | null | undefined): string {
  if (!estado) return 'Sin validación';

  const labels: Record<string, string> = {
    SIN_VALIDACION: 'Sin validación',
    VALIDADO: 'Validado',
    RECHAZADO: 'Rechazado',
    PENDIENTE_VALIDACION: 'Pendiente de validación',
  };

  return labels[estado] || estado;
}

manejarCambioSubcategoria(): void {
  this.cargarBitacoras();
}

}