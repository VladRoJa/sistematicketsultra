// frontend\src\app\pm\pm-consulta-historial\pm-consulta-historial.component.ts


import { Component, OnInit, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule, FormControl, ReactiveFormsModule } from '@angular/forms';
import { Observable } from 'rxjs';
import { map, startWith } from 'rxjs/operators';

import { MatAutocompleteModule } from '@angular/material/autocomplete';
import { MatCardModule } from '@angular/material/card';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatButtonModule } from '@angular/material/button';
import { MatTableModule } from '@angular/material/table';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';

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
  ],
  templateUrl: './pm-consulta-historial.component.html',
  styleUrls: ['./pm-consulta-historial.component.css'],
})
export class PmConsultaHistorialComponent implements OnInit {
  private pmService = inject(PmPreventivoService);
  private snack = inject(MatSnackBar);

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

  readonly displayedColumns = [
    'fecha',
    'equipo',
    'sucursal',
    'resultado',
    'estado_validacion',
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
        this.fechaHasta || null
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

    this.pmService.getBitacoraDetalle(row.id).subscribe({
      next: (detalle) => {
        this.detalleBitacoraPm = detalle;
        this.bitacoraSeleccionadaId = row.id;
        this.detalleBitacoraLoading = false;
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
}