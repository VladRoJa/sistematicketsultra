// frontend\src\app\pm\pm-bitacoras-mobile\pm-bitacoras-mobile.component.ts

import { Component, inject, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormBuilder, Validators, ReactiveFormsModule } from '@angular/forms';
import { HttpClient } from '@angular/common/http';

import { MatCardModule } from '@angular/material/card';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatSelectModule } from '@angular/material/select';
import { MatButtonModule } from '@angular/material/button';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { MatAutocompleteModule } from '@angular/material/autocomplete';
import { PmInventarioService, PmEquipoItem } from './services/pm-inventario.service';
import { debounceTime, distinctUntilChanged, map, startWith } from 'rxjs/operators';
import { BehaviorSubject, combineLatest, Observable } from 'rxjs';

import { SessionService } from '../../core/auth/session.service';

type ResultadoBitacora = 'OK' | 'FALLA' | 'OBS';

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
  sucursalesList: Array<{ sucursal_id: number; sucursal: string }> = [];

  equipos: PmEquipoItem[] = [];
  private equipos$ = new BehaviorSubject<PmEquipoItem[]>([]);
  equiposLoading = false;

  // ✅ Endpoint backend (proxy /api)
  private readonly endpoint = '/api/pm/mobile/bitacoras';

  loading = false;
  lastId: number | null = null;
  sucursalNombre = '';
  private sucursalesMap = new Map<number, string>();
  puedeCambiarSucursal = false;

  equipoCtrl = this.fb.control<PmEquipoItem | string>(''); // texto que escribe el usuario
  filteredEquipos$!: Observable<PmEquipoItem[]>;
  
  
  ngOnInit(): void {
    // ✅ cargar catálogo y nombre de sucursal
    this.cargarCatalogoSucursales();
    // Carga inicial
    const s = this.form.get('sucursal_id')?.value;
    const user = this.session.getUser();
    const rol = (user?.rol || '').toString().toUpperCase();

    this.puedeCambiarSucursal = rol === 'MANTENIMIENTO' || rol === 'SR_MANTENIMIENTO';
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
    this.pmInventario.listarEquipos({ sucursal_id: sucursalId, tipo: 'MAQUINA' }).subscribe({
      next: (rows) => {
        this.equipos = rows || [];
        this.equipos$.next(this.equipos);
        this.equiposLoading = false;
        this.equipoCtrl.setValue('', { emitEvent: true });
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
    resultado: ['OK' as ResultadoBitacora, [Validators.required]],
    notas: [''],

    // MVP checks (puedes cambiarlos luego por checklist real)
    check_limpieza: [true],
    check_ajustes: [false],
    check_ruidos: [false],
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
      resultado: v.resultado,
      notas: v.notas || '',
      checks: {
        limpieza: !!v.check_limpieza,
        ajustes: !!v.check_ajustes,
        ruidos: !!v.check_ruidos,
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

      // ✅ limpiar para nueva captura (manteniendo defaults útiles)
      const currentSucursal = this.form.get('sucursal_id')?.value;

      this.form.reset({
        inventario_id: null,
        sucursal_id: currentSucursal,          // mantener sucursal seleccionada
        fecha: this.todayYYYYMMDD(),           // hoy
        resultado: 'OK' as ResultadoBitacora,  // default
        notas: '',
        check_limpieza: true,
        check_ajustes: false,
        check_ruidos: false,
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
  this.http.get<Array<{ sucursal_id: number; sucursal: string }>>('/api/inventario/sucursales')
    .subscribe({
    next: (rows) => {
      const user = this.session.getUser();
      const rol = (user?.rol || '').toString().toUpperCase();
      const allowedIds = (user?.sucursales_ids || []).map((x: any) => Number(x));
      const userSucursalId = Number(user?.sucursal_id);

      let filtered = rows || [];

      if (rol === 'SR_MANTENIMIENTO') {
        filtered = filtered.filter(r => allowedIds.includes(Number(r.sucursal_id)));
      } else if (rol === 'AUX_MANTENIMIENTO') {
        filtered = filtered.filter(r => Number(r.sucursal_id) === userSucursalId);
      }
      // MANTENIMIENTO: no filtra (ve todas)

      this.sucursalesList = filtered.map(r => ({
        sucursal_id: Number(r.sucursal_id),
        sucursal: r.sucursal
      }));

      this.sucursalesMap.clear();
      for (const r of filtered) {
        this.sucursalesMap.set(Number(r.sucursal_id), r.sucursal);
      }

      // refresca nombre con el sucursal_id actual (si ya existe)
      this.actualizarSucursalNombre(this.form?.value?.sucursal_id);
    },
      error: () => {
        // si falla, no rompemos la pantalla; solo dejamos nombre vacío
        this.sucursalNombre = '';
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
}