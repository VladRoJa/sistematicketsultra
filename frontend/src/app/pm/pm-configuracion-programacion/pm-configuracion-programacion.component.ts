//frontend\src\app\pm\pm-configuracion-programacion\pm-configuracion-programacion.component.ts


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
import { InventarioService } from '../../services/inventario.service';
import { PmPreventivoService } from '../../services/pm-preventivo.service';
import {
  PmConfiguracionResumen,
  SucursalOption,
} from '../../models/pm-preventivo.model';

@Component({
  selector: 'app-pm-configuracion-programacion',
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
  templateUrl: './pm-configuracion-programacion.component.html',
  styleUrls: ['./pm-configuracion-programacion.component.css'],
})
export class PmConfiguracionProgramacionComponent implements OnInit {
  private pmService = inject(PmPreventivoService);
  private snack = inject(MatSnackBar);
  private inventarioService = inject(InventarioService);

  loading = false;
  saving = false;
  sucursalesLoading = false;

  sucursalesList: SucursalOption[] = [];
  filteredSucursales$!: Observable<SucursalOption[]>;
  sucursalCtrl = new FormControl<string | SucursalOption>('');
  selectedSucursalId: number | null = null;

  inventarioIdInput: number | null = null;
  frecuenciaDiasInput: number | null = null;
  activoInput = true;

  configuraciones: PmConfiguracionResumen[] = [];

  inventarioOptions: any[] = [];
  inventarioLoading = false;

  equipoCtrl = new FormControl<string | any>('');
  filteredInventarioOptions$!: Observable<any[]>;

  

  readonly displayedColumns = [
    'equipo',
    'sucursal',
    'frecuencia_dias',
    'activo',
    'accion',

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

  this.filteredInventarioOptions$ = this.equipoCtrl.valueChanges.pipe(
    startWith(''),
    map((value) => {
      const term = (typeof value === 'string'
        ? value
        : `${value?.codigo_interno || ''} ${value?.nombre || ''}`
      )
        .toLowerCase()
        .trim();

      if (!term) {
        return this.inventarioOptions;
      }

      return this.inventarioOptions.filter((item) =>
        `${item.codigo_interno || ''} ${item.nombre || ''}`.toLowerCase().includes(term)
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
        const unica = this.sucursalesList[0];
        this.selectedSucursalId = unica.sucursal_id;
        this.sucursalCtrl.setValue(unica, { emitEvent: false });
        this.cargarInventarioSucursal();
        this.cargarConfiguraciones();
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
    this.inventarioIdInput = null;
    this.equipoCtrl.setValue('', { emitEvent: false });
    this.cargarInventarioSucursal();
    this.cargarConfiguraciones();
}

  sucursalDisplay(value: SucursalOption | string | null): string {
    if (!value) return '';
    return typeof value === 'string' ? value : value.sucursal;
  }

  cargarConfiguraciones(): void {
    if (!this.selectedSucursalId) {
      this.snack.open('Selecciona una sucursal', 'OK', { duration: 2000 });
      return;
    }

    this.loading = true;
    this.configuraciones = [];

    this.pmService.listarConfiguracionesPm(this.selectedSucursalId).subscribe({
      next: (rows) => {
        this.configuraciones = rows || [];
        this.loading = false;
      },
      error: (err) => {
        this.loading = false;
        const msg =
          err?.error?.detail ||
          err?.error?.message ||
          'No se pudieron cargar las configuraciones PM';
        this.snack.open(msg, 'OK', { duration: 3500 });
      },
    });
  }

  crearConfiguracion(): void {
    if (!this.selectedSucursalId || !this.inventarioIdInput || !this.frecuenciaDiasInput) {
      this.snack.open('Completa sucursal, inventario_id y frecuencia_dias', 'OK', {
        duration: 2500,
      });
      return;
    }

    this.saving = true;

    this.pmService.crearConfiguracionPm({
      inventario_id: this.inventarioIdInput,
      sucursal_id: this.selectedSucursalId,
      frecuencia_dias: this.frecuenciaDiasInput,
      activo: this.activoInput,
    }).subscribe({
      next: () => {
        this.saving = false;
        this.inventarioIdInput = null;
        this.equipoCtrl.setValue('', { emitEvent: false });
        this.frecuenciaDiasInput = null;
        this.activoInput = true;

        this.snack.open('Configuración PM creada', 'OK', { duration: 2500 });
        this.cargarConfiguraciones();
      },
      error: (err) => {
        this.saving = false;
        const msg =
          err?.error?.detail ||
          err?.error?.message ||
          'No se pudo crear la configuración PM';
        this.snack.open(msg, 'OK', { duration: 3500 });
      },
    });
  }

  equipoLabel(row: PmConfiguracionResumen): string {
    return [row.codigo_interno, row.nombre].filter(Boolean).join(' — ');
  }

  activoLabel(row: PmConfiguracionResumen): string {
    return row.activo ? 'Sí' : 'No';
  }

  get inventarioSelectDisabled(): boolean {
  return this.inventarioLoading || !this.selectedSucursalId || this.inventarioOptions.length === 0;
}

  private cargarInventarioSucursal(): void {
  if (!this.selectedSucursalId) {
    this.inventarioOptions = [];
    return;
  }

  this.inventarioLoading = true;
  this.inventarioOptions = [];

  this.inventarioService.obtenerInventarioPorSucursal(this.selectedSucursalId).subscribe({
    next: (rows) => {
      this.inventarioOptions = rows || [];
      this.inventarioLoading = false;
    },
    error: () => {
      this.inventarioOptions = [];
      this.inventarioLoading = false;
      this.snack.open('No se pudo cargar el inventario de la sucursal', 'OK', {
        duration: 3000,
      });
    },
  });
}

equipoDisplay(value: any): string {
  if (!value) return '';
  if (typeof value === 'string') return value;
  return [value.codigo_interno, value.nombre].filter(Boolean).join(' — ');
}

onEquipoSelected(item: any): void {
  this.inventarioIdInput = item?.id ?? null;
  this.equipoCtrl.setValue(item, { emitEvent: false });
}

toggleActivoConfiguracion(row: PmConfiguracionResumen): void {
  this.pmService.actualizarConfiguracionPm(row.id, {
    activo: !row.activo,
  }).subscribe({
    next: () => {
      this.snack.open(
        row.activo ? 'Configuración PM desactivada' : 'Configuración PM activada',
        'OK',
        { duration: 2500 }
      );
      this.cargarConfiguraciones();
    },
    error: (err) => {
      const msg =
        err?.error?.detail ||
        err?.error?.message ||
        'No se pudo actualizar la configuración PM';
      this.snack.open(msg, 'OK', { duration: 3500 });
    },
  });
}
}