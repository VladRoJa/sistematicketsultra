// frontend\src\app\pm\pm-bitacoras-mobile\pm-bitacoras-mobile.component.ts

import { Component, inject, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormBuilder, Validators, ReactiveFormsModule } from '@angular/forms';
import { HttpClient } from '@angular/common/http';
import { environment } from 'src/environments/environment';
import { MatCardModule } from '@angular/material/card';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatSelectModule } from '@angular/material/select';
import { MatButtonModule } from '@angular/material/button';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { MatAutocompleteModule } from '@angular/material/autocomplete';
import { PmInventarioService, PmEquipoItem } from './services/pm-inventario.service';
import { PmPreventivoService } from '../../services/pm-preventivo.service';
import { debounceTime, distinctUntilChanged, map, startWith } from 'rxjs/operators';
import { BehaviorSubject, combineLatest, Observable } from 'rxjs';
import { ActivatedRoute, Router  } from '@angular/router';


import { SessionService } from '../../core/auth/session.service';

type ResultadoBitacora = 'OK' | 'FALLA' | 'OBS';
type TipoMantenimiento = 'CORRECTIVO' | 'PREVENTIVO' | 'ESTETICO';
type VentanaPreventiva = 'ATRASADOS' | 'HOY' | 'PROXIMOS_7' | 'PROXIMOS_14';



@Component({
  selector: 'app-pm-bitacoras-mobile',
  standalone: true,
  imports: [
    CommonModule,
    ReactiveFormsModule,

    MatCardModule,
    MatFormFieldModule,
    MatInputModule,
    MatSelectModule,
    MatButtonModule,
    MatSnackBarModule,
    MatAutocompleteModule,
  ],
  templateUrl: './pm-bitacoras-mobile.component.html',
  styleUrls: ['./pm-bitacoras-mobile.component.css'],
})
export class PmBitacorasMobileComponent implements OnInit {
  private fb = inject(FormBuilder);
  private http = inject(HttpClient);
  private snack = inject(MatSnackBar);
  private session = inject(SessionService);
  private pmInventario = inject(PmInventarioService);
  private pmPreventivo = inject(PmPreventivoService);
  private route = inject(ActivatedRoute);
  private router = inject(Router);
  
  sucursalesList: Array<{ sucursal_id: number; sucursal: string }> = [];

  equipos: PmEquipoItem[] = [];
  private equipos$ = new BehaviorSubject<PmEquipoItem[]>([]);
  equiposLoading = false;

  private readonly endpoint = `${environment.apiUrl}/pm/mobile/bitacoras`;

  loading = false;
  lastId: number | null = null;
  sucursalNombre = '';
  private sucursalesMap = new Map<number, string>();
  puedeCambiarSucursal = false;
  prefillInventarioId: number | null = null;
  prefillSucursalId: number | null = null;
  prefillModo: string | null = null;


  equipoCtrl = this.fb.control<PmEquipoItem | string>(''); // texto que escribe el usuario
  filteredEquipos$!: Observable<PmEquipoItem[]>;
  
  readonly tiposMantenimiento: TipoMantenimiento[] = [
  'CORRECTIVO',
  'PREVENTIVO',
  'ESTETICO',
];

  readonly ventanasPreventivo = [
    { value: 'ATRASADOS', label: 'Solo atrasados' },
    { value: 'HOY', label: 'Solo hoy' },
    { value: 'PROXIMOS_7', label: 'Próximos 7 días' },
    { value: 'PROXIMOS_14', label: 'Próximos 14 días' },
  ];
  
  
  ngOnInit(): void {
    this.prefillSucursalId = this.toNumberOrNull(this.route.snapshot.queryParamMap.get('sucursalId'));
    this.prefillInventarioId = this.toNumberOrNull(this.route.snapshot.queryParamMap.get('inventarioId'));
    this.prefillModo = this.route.snapshot.queryParamMap.get('modo');
    if (this.prefillSucursalId) {
      this.form.patchValue({ sucursal_id: this.prefillSucursalId }, { emitEvent: false });
    }
    // ✅ cargar catálogo y nombre de sucursal
    this.cargarCatalogoSucursales();
    // Carga inicial
    const s = this.form.get('sucursal_id')?.value;
    const user = this.session.getUser();
    const rol = (user?.rol || '').toString().toUpperCase();

    this.puedeCambiarSucursal = ['MANTENIMIENTO', 'SR_MANTENIMIENTO', 'SISTEMAS', 'TECNICO'].includes(rol);
    if (s) this.cargarEquipos(Number(s));

    // Recargar cuando cambia sucursal (debounce para UX)
    this.form.get('sucursal_id')?.valueChanges
    .pipe(
        debounceTime(150),
        // ✅ normaliza para que "1" y 1 sean lo mismo
        map((v) => (v === null || v === undefined ? null : Number(v))),
        distinctUntilChanged(),
    )
.subscribe((suc) => {
  this.form.patchValue({ inventario_id: null }, { emitEvent: false });

  // ✅ actualiza el nombre visible
  this.actualizarSucursalNombre(suc);

  if (suc) this.cargarEquipos(suc);
  else this.equipos = [];
});

this.form.get('tipo_mantenimiento')?.valueChanges
  .pipe(distinctUntilChanged())
  .subscribe(() => {
    const suc = Number(this.form.get('sucursal_id')?.value);

    this.form.patchValue({ inventario_id: null }, { emitEvent: false });
    this.equipoCtrl.setValue('', { emitEvent: true });

    if (suc) {
      this.cargarEquipos(suc);
    } else {
      this.equipos = [];
      this.equipos$.next([]);
    }
  });

this.form.get('ventana_preventivo_dias')?.valueChanges
  .pipe(distinctUntilChanged())
  .subscribe(() => {
    if (!this.esTipoMantenimientoPreventivo()) {
      return;
    }

    const suc = Number(this.form.get('sucursal_id')?.value);

    this.form.patchValue({ inventario_id: null }, { emitEvent: false });
    this.equipoCtrl.setValue('', { emitEvent: true });

    if (suc) {
      this.cargarEquipos(suc);
    } else {
      this.equipos = [];
      this.equipos$.next([]);
    }
  });



    this.form.get('inventario_id')?.valueChanges.subscribe(v => {
});
this.filteredEquipos$ = combineLatest([
  this.equipoCtrl.valueChanges.pipe(startWith('')),
  this.equipos$.asObservable(),
]).pipe(
  map(([value, equipos]) => {
    const term = (typeof value === 'string' ? value : this.equipoLabel(value || ({} as any)))
      .toString()
      .toLowerCase()
      .trim();

    if (!term) return equipos;

    return equipos.filter(e => {
      const codigo = (e.codigo_interno || '').toLowerCase();
      const nombre = (e.nombre || '').toLowerCase();
      return codigo.includes(term) || nombre.includes(term);
    });
  })
);
  }

private cargarEquipos(sucursalId: number): void {
  this.equiposLoading = true;

const request$ = this.esTipoMantenimientoPreventivo()
  ? this.pmInventario.listarEquiposPreventivosOperativos(
      sucursalId,
      this.obtenerVentanaPreventivaDias(),
      this.obtenerVentanaPreventivaModo()
    )
  : this.pmInventario.listarEquiposOperativosSucursal(sucursalId);

  request$.subscribe({
    next: (rows) => {
      this.equipos = rows || [];
      this.equipos$.next(this.equipos);
      this.equiposLoading = false;

      if (this.prefillInventarioId) {
        const equipoPrefill = this.equipos.find(
          e => Number(e.id) === this.prefillInventarioId || Number(e.inventario_id) === this.prefillInventarioId
        );

        if (equipoPrefill) {
          this.onEquipoSelected(equipoPrefill);
        } else {
          this.equipoCtrl.setValue('', { emitEvent: true });
        }
      } else {
        this.equipoCtrl.setValue('', { emitEvent: true });
      }
    },
    error: () => {
      this.equipos = [];
      this.equipos$.next([]);
      this.equiposLoading = false;
      this.snack.open('No se pudo cargar inventario', 'OK', { duration: 2500 });
    },
  });
}

  equipoLabel(e: PmEquipoItem): string {
    const parts = [
      e.codigo_interno,
      e.nombre,
      e.marca,
      e.modelo,
    ].filter(Boolean);
    return parts.join(' • ') || `ID ${e.inventario_id}`;
  }

  // Defaults útiles desde sesión
  private defaultSucursalId(): number | null {
    const user = this.session.getUser();
    const s = user?.sucursal_id;
    return typeof s === 'number' ? s : (s ? Number(s) : null);
  }

  form = this.fb.group({
    inventario_id: [null as number | null, [Validators.required]],
    sucursal_id: [this.defaultSucursalId(), [Validators.required]],
    fecha: [this.todayYYYYMMDD(), [Validators.required]],
    tipo_mantenimiento: ['CORRECTIVO' as TipoMantenimiento, [Validators.required]],
    ventana_preventivo_dias: ['HOY' as string | null],
    resultado: ['OK' as ResultadoBitacora, [Validators.required]],
    notas: [''],

    // MVP checks (puedes cambiarlos luego por checklist real)
    check_limpieza: [true],
    check_ajuste: [false],
    check_revision: [false],
    check_lubricacion: [false],

    
  });

  private todayYYYYMMDD(): string {
    const d = new Date();
    const yyyy = d.getFullYear();
    const mm = String(d.getMonth() + 1).padStart(2, '0');
    const dd = String(d.getDate()).padStart(2, '0');
    return `${yyyy}-${mm}-${dd}`;
  }

  buildPayload(): any {
    const v = this.form.getRawValue();

    return {
      inventario_id: v.inventario_id,
      sucursal_id: v.sucursal_id,
      fecha: v.fecha,
      tipo_mantenimiento: v.tipo_mantenimiento,
      resultado: v.resultado,
      notas: v.notas || '',
      checks: {
        limpieza: !!v.check_limpieza,
        ajustes: !!v.check_ajuste,
        revision: !!v.check_revision,
        lubricacion: !!v.check_lubricacion,
      },
    };
  }

  async guardar(): Promise<void> {
    this.lastId = null;

    if (this.form.invalid) {
      this.form.markAllAsTouched();
      this.snack.open('Completa los campos requeridos', 'OK', { duration: 2500 });
      return;
    }

    const payload = this.buildPayload();

    this.loading = true;
    this.http.post<{ id: number; msg: string }>(this.endpoint, payload).subscribe({
      next: (res) => {
    this.loading = false;
    this.lastId = res?.id ?? null;
    this.snack.open(res?.msg || 'Bitácora guardada', 'OK', { duration: 2500 });

    if (this.esFlujoPreventivo) {
      this.router.navigate(['/pm/escritorio-preventivo']);
      return;
    }

    // ✅ limpiar para nueva captura (manteniendo defaults útiles)
    const currentSucursal = this.form.get('sucursal_id')?.value;

    this.form.reset({
      inventario_id: null,
      sucursal_id: currentSucursal,
      fecha: this.todayYYYYMMDD(),
      tipo_mantenimiento: 'CORRECTIVO' as TipoMantenimiento,
      resultado: 'OK' as ResultadoBitacora,
      notas: '',
      check_limpieza: true,
      check_ajuste: false,
      check_revision: false,
      check_lubricacion: false,
    });

    // limpiar el input del autocomplete
    this.equipoCtrl.setValue('', { emitEvent: true });
      },
      error: (err) => {
        this.loading = false;
        const msg =
          err?.error?.detail ||
          err?.error?.message ||
          'Error al guardar bitácora';
        this.snack.open(msg, 'OK', { duration: 3500 });
      },
    });
  }

private cargarCatalogoSucursales(): void {
  this.pmPreventivo.getSucursalesPermitidas().subscribe({
    next: (rows) => {
      const list = (rows || []).map(r => ({
        sucursal_id: Number(r.sucursal_id),
        sucursal: r.sucursal
      }));

      this.sucursalesList = list;

      this.sucursalesMap.clear();
      for (const r of list) {
        this.sucursalesMap.set(Number(r.sucursal_id), r.sucursal);
      }

      const current = Number(this.form?.value?.sucursal_id);
      const allowedIds = new Set(list.map(x => x.sucursal_id));

      if (!current || Number.isNaN(current) || !allowedIds.has(current)) {
        const first = list[0]?.sucursal_id ?? null;
        this.form.patchValue({ sucursal_id: first }, { emitEvent: true });
      } else {
        this.actualizarSucursalNombre(current);
      }
    },
    error: () => {
      this.sucursalNombre = '';
      this.sucursalesList = [];
    }
  });
}

private actualizarSucursalNombre(sucursalId: any): void {
  const id = Number(sucursalId);
  if (!id || Number.isNaN(id)) {
    this.sucursalNombre = '';
    return;
  }
  this.sucursalNombre = this.sucursalesMap.get(id) ?? '';
}

onEquipoSelected(equipo: PmEquipoItem): void {
  this.form.patchValue({ inventario_id: equipo.id }, { emitEvent: false });
  this.equipoCtrl.setValue(equipo, { emitEvent: false }); // fija el input con displayWith
  console.log('inventario_id real ->', this.form.get('inventario_id')?.value);
}

equipoDisplay = (value: PmEquipoItem | string | null): string => {
  if (!value) return '';
  return typeof value === 'string' ? value : this.equipoLabel(value);
};

mostrarMetaPreventiva(item: PmEquipoItem): boolean {
  return this.esTipoMantenimientoPreventivo() && !!item?.estado_pm;
}

formatearFechaCorta(fechaIso: string | null | undefined): string {
  if (!fechaIso) {
    return '';
  }

  const [anio, mes, dia] = fechaIso.split('-');
  if (!anio || !mes || !dia) {
    return fechaIso;
  }

  return `${dia}/${mes}`;
}

obtenerMetaPreventiva(item: PmEquipoItem): string {
  const estado = (item?.estado_pm || '').toUpperCase();
  const fecha = this.formatearFechaCorta(item?.proxima_fecha);

  if (estado === 'HOY') {
    return 'PM hoy';
  }

  if (estado === 'ATRASADO') {
    return fecha ? `PM atrasado · ${fecha}` : 'PM atrasado';
  }

  if (estado === 'PROXIMO') {
    return fecha ? `Próximo · ${fecha}` : 'Próximo PM';
  }

  return '';
}

private toNumberOrNull(value: unknown): number | null {
  if (value === null || value === undefined || value === '') return null;
  const n = Number(value);
  return Number.isNaN(n) ? null : n;
}

get esFlujoPreventivo(): boolean {
  return this.prefillModo === 'preventivo';
}

tipoMantenimientoLabel(tipo: TipoMantenimiento | string | null): string {
  if (!tipo) return '';

  const labels: Record<string, string> = {
    CORRECTIVO: 'Correctivo',
    PREVENTIVO: 'Preventivo',
    ESTETICO: 'Estético',
    MEJORA: 'Mejora',
  };

  return labels[tipo] || tipo;
}

private esTipoMantenimientoPreventivo(): boolean {
  return this.form.get('tipo_mantenimiento')?.value === 'PREVENTIVO';
}

private obtenerVentanaPreventivaDias(): number {
  const valor = this.form.get('ventana_preventivo_dias')?.value;

  if (valor === 'PROXIMOS_14') {
    return 14;
  }

  if (valor === 'PROXIMOS_7') {
    return 7;
  }

  return 1;
}

private obtenerVentanaPreventivaModo(): VentanaPreventiva {
  const valor = this.form.get('ventana_preventivo_dias')?.value;

  if (valor === 'ATRASADOS') {
    return 'ATRASADOS';
  }

  if (valor === 'HOY') {
    return 'HOY';
  }

  if (valor === 'PROXIMOS_14') {
    return 'PROXIMOS_14';
  }

  return 'PROXIMOS_7';
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

}