// frontend-angular/src/app/pantalla-crear-ticket/formularios-crear-ticket/mantenimiento-aparatos/mantenimiento-aparatos.component.ts

import { Component, Input, Output, EventEmitter, OnInit, OnDestroy } from '@angular/core';
import { HttpClient, HttpHeaders } from '@angular/common/http';
import { environment } from 'src/environments/environment';
import { FormGroup, FormControl, FormBuilder, Validators, ReactiveFormsModule, FormsModule } from '@angular/forms';
import { CommonModule } from '@angular/common';
import { Subscription } from 'rxjs';

// Services & Components
import { SucursalesService } from 'src/app/services/sucursales.service';
import { EquiposService } from 'src/app/services/equipos.service';
import { SelectorEquipoComponent } from 'src/app/components/selector-equipo/selector-equipo.component';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatSelectModule } from '@angular/material/select';
import { MatCheckboxModule } from '@angular/material/checkbox';
import { MatButtonModule } from '@angular/material/button';

import {
  limpiarCamposDependientes,
  emitirPayloadFormulario,
  DEPARTAMENTO_IDS
} from 'src/app/utils/formularios.helper';

interface EquipoTapizado {
  id: number;
  nombre: string;
  codigo_interno?: string;
  marca?: string;
  categoria?: string;
  familia_equipo_id?: number | null;
  familia_equipo?: { id: number; nombre: string } | null;
}

@Component({
  selector: 'app-mantenimiento-aparatos',
  standalone: true,
  imports: [
    CommonModule,
    FormsModule,
    ReactiveFormsModule,
    SelectorEquipoComponent,
    MatFormFieldModule,
    MatInputModule,
    MatSelectModule,
    MatCheckboxModule,
    MatButtonModule,
  ],
  templateUrl: './mantenimiento-aparatos.component.html',
  styleUrls: ['./mantenimiento-aparatos.component.css'],
})
export class MantenimientoAparatosComponent implements OnInit, OnDestroy {
  @Input() parentForm!: FormGroup;
  @Input() tipo: 'aparato' | 'dispositivo' = 'aparato';
  @Output() formularioValido = new EventEmitter<any>();

  sucursales: any[] = [];
  equipos: any[] = [];
  sucursalSeleccionada!: number;

  // M3: la opción sólo aparece cuando Flask confirma su activación.
  tapizadoHabilitado = false;
  modoTapizado = false;
  aparatosSeleccionados: EquipoTapizado[] = [];
  filtroTapizado = new FormControl('', { nonNullable: true });
  filtroCategoriaTapizado = new FormControl('', { nonNullable: true });
  filtroFamiliaTapizado = new FormControl('', { nonNullable: true });
  private readonly maxAparatosTapizado = 50;
  private configSub?: Subscription;
  private equiposReqSub?: Subscription;

  get categoriasDisponiblesTapizado(): string[] {
    return [...new Set(this.equipos
      .filter(eq => !this.filtroFamiliaTapizado.value ||
        String(eq.familia_equipo_id ?? '') === this.filtroFamiliaTapizado.value)
      .map(eq => String(eq.categoria || 'Sin categoría'))
    )].sort();
  }

  get familiasDisponiblesTapizado(): Array<{ id: string; nombre: string }> {
    const porId = new Map<string, string>();
    this.equipos
      .filter(eq => !this.filtroCategoriaTapizado.value ||
        String(eq.categoria || 'Sin categoría') === this.filtroCategoriaTapizado.value)
      .forEach(eq => {
        if (eq.familia_equipo_id != null) {
          porId.set(String(eq.familia_equipo_id), eq.familia_equipo?.nombre || 'Familia ' + eq.familia_equipo_id);
        }
      });
    return Array.from(porId, ([id, nombre]) => ({ id, nombre }))
      .sort((a, b) => a.nombre.localeCompare(b.nombre));
  }

  get aparatosDisponiblesTapizado(): EquipoTapizado[] {
    const filtro = this.normalizarTexto(this.filtroTapizado.value);
    const categoria = this.filtroCategoriaTapizado.value;
    const familia = this.filtroFamiliaTapizado.value;
    return this.equipos.filter(eq => {
      const coincide = !filtro || this.normalizarTexto(
        `${eq.nombre || ''} ${eq.codigo_interno || ''} ${eq.marca || ''}`
      ).includes(filtro);
      return coincide
        && (!categoria || String(eq.categoria || 'Sin categoría') === categoria)
        && (!familia || String(eq.familia_equipo_id ?? '') === familia)
        && !this.aparatosSeleccionados.some(selected => selected.id === Number(eq.id));
    }).slice(0, 25);
  }

  private normalizarTexto(value: string): string {
    return (value || '').toLowerCase().normalize('NFD')
      .replace(/[\u0300-\u036f]/g, '').trim();
  }

  private formSub?: Subscription;
  private sucursalSub?: Subscription;

  constructor(
    private fb: FormBuilder,
    private sucursalesService: SucursalesService,
    private equiposService: EquiposService,
    private http: HttpClient
  ) {}

ngOnInit(): void {
  if (!this.parentForm) {
    console.error('[MantenimientoAparatos] parentForm no definido');
    return;
  }

  const sucursalCtrl = this.parentForm.get('sucursal_id');
  if (!sucursalCtrl) {
    console.error('[MantenimientoAparatos] El control sucursal_id no existe en parentForm');
    return;
  }

  // --- Estado de disponibilidad: el servidor es la autoridad del rollout.
  const token = localStorage.getItem('token');
  const headers = token
    ? new HttpHeaders().set('Authorization', `Bearer ${token}`)
    : new HttpHeaders();
  this.configSub = this.http.get<{ habilitado: boolean }>(
    `${environment.apiUrl}/tickets/tapizado-disponible`, { headers }
  ).subscribe({
    next: result => { this.tapizadoHabilitado = result.habilitado === true; },
    error: () => { this.tapizadoHabilitado = false; },
  });

  if (!this.parentForm.contains('tipo_trabajo')) {
    this.parentForm.addControl('tipo_trabajo', this.fb.control(null));
  }
  if (!this.parentForm.contains('aparatos_ids')) {
    this.parentForm.addControl('aparatos_ids', this.fb.control([]));
  }

  // --- Inicializar controles propios ---
  this.parentForm.addControl('detalle', this.fb.control(''));
  this.parentForm.addControl('subcategoria', this.fb.control(''));
  if (!this.parentForm.contains('aparato_id')) {
    this.parentForm.addControl(
      'aparato_id',
      this.fb.control(null, this.tipo === 'aparato' ? [Validators.required] : [])
    );
  } else if (this.tipo === 'aparato') {
    this.parentForm.get('aparato_id')?.addValidators(Validators.required);
    this.parentForm.get('aparato_id')?.updateValueAndValidity({ emitEvent: false });
  }

  // --- Detectar sucursal desde el padre (ya viene en parentForm) ---
  this.sucursalSeleccionada = sucursalCtrl.value;

  // Carga inicial de equipos
  this.cargarEquiposPorSucursal(this.sucursalSeleccionada);

  // Escucha cambios de sucursal desde el padre
  this.sucursalSub = sucursalCtrl.valueChanges.subscribe((sucId: number) => {
    this.sucursalSeleccionada = sucId;
    // Reset controles dependientes
    this.parentForm.get('detalle')!.reset();
    this.parentForm.get('subcategoria')!.reset();
    this.parentForm.get('aparato_id')!.reset();
    this.aparatosSeleccionados = [];
    this.filtroTapizado.setValue('');
    this.filtroCategoriaTapizado.setValue('');
    this.filtroFamiliaTapizado.setValue('');
    this.sincronizarMultiaparato();
    this.cargarEquiposPorSucursal(sucId);
  });

  // Emite validez al padre
  this.formSub = this.parentForm.valueChanges.subscribe(() => {
    emitirPayloadFormulario(
      this.parentForm,
      DEPARTAMENTO_IDS.mantenimiento,
      this.formularioValido
    );
  });
}


  ngOnDestroy(): void {
    this.formSub?.unsubscribe();
    this.sucursalSub?.unsubscribe();
    this.configSub?.unsubscribe();
    this.equiposReqSub?.unsubscribe();
    this.aparatosSeleccionados = [];
    this.modoTapizado = false;
    this.parentForm.get('tipo_trabajo')?.setValue(null, { emitEvent: false });
    this.parentForm.get('aparatos_ids')?.clearValidators();
    this.parentForm.get('aparatos_ids')?.setValue([], { emitEvent: false });
    this.parentForm.get('aparatos_ids')?.updateValueAndValidity({ emitEvent: false });
    // Evita que se “hereden” valores a otros flujos
    ['detalle','subcategoria','aparato_id'].forEach(c => {
      if (this.parentForm.contains(c)) this.parentForm.removeControl(c);
    });
  }

  onEquipoSeleccionado(eq: any) {
    if (this.modoTapizado) return;
    if (!eq) {
      this.parentForm.get('detalle')!.reset();
      this.parentForm.get('subcategoria')!.reset();
      this.parentForm.get('aparato_id')!.reset();
      return;
    }
    // Rellena los campos desde el objeto equipo
    this.parentForm.get('detalle')!.setValue(`${eq.nombre} (${eq.codigo_interno})`);
    this.parentForm.get('subcategoria')!.setValue(eq.categoria || 'General');
    this.parentForm.get('aparato_id')!.setValue(eq.id);
    limpiarCamposDependientes(this.parentForm, [
      'descripcion_general',
      'necesita_refaccion',
      'descripcion_refaccion'
    ]);
  }

  cambiarModoTapizado(activar: boolean): void {
    if (activar && !this.tapizadoHabilitado) return;
    this.modoTapizado = activar;
    this.aparatosSeleccionados = [];
    this.filtroTapizado.setValue('');
    this.filtroCategoriaTapizado.setValue('');
    this.filtroFamiliaTapizado.setValue('');
    this.parentForm.get('tipo_trabajo')?.setValue(activar ? 'TAPIZADO' : null);
    const lista = this.parentForm.get('aparatos_ids');
    if (activar) {
      lista?.setValidators([Validators.required, Validators.minLength(1)]);
    } else {
      lista?.clearValidators();
    }
    this.parentForm.get('aparato_id')?.reset();
    this.parentForm.get('detalle')?.reset();
    this.parentForm.get('subcategoria')?.reset();
    this.sincronizarMultiaparato();
  }

  cambiarCategoriaTapizado(categoria: string): void {
    this.filtroCategoriaTapizado.setValue(categoria);
    if (!this.familiasDisponiblesTapizado.some(f => f.id === this.filtroFamiliaTapizado.value)) {
      this.filtroFamiliaTapizado.setValue('');
    }
  }

  cambiarFamiliaTapizado(familia: string): void {
    this.filtroFamiliaTapizado.setValue(familia);
    if (!this.categoriasDisponiblesTapizado.includes(this.filtroCategoriaTapizado.value)) {
      this.filtroCategoriaTapizado.setValue('');
    }
  }

  alternarAparatoTapizado(equipo: EquipoTapizado, marcado: boolean): void {
    const id = Number(equipo.id);
    if (!this.modoTapizado || !Number.isInteger(id) || id <= 0) return;
    if (!this.equipos.some(item => Number(item.id) === id)) return;
    const existe = this.aparatosSeleccionados.some(item => item.id === id);
    if (marcado && !existe && this.aparatosSeleccionados.length < this.maxAparatosTapizado) {
      this.aparatosSeleccionados = [...this.aparatosSeleccionados, { ...equipo, id }];
    } else if (!marcado && existe) {
      this.aparatosSeleccionados = this.aparatosSeleccionados.filter(item => item.id !== id);
    }
    this.sincronizarMultiaparato();
  }

  eliminarAparatoTapizado(equipo: EquipoTapizado): void {
    this.alternarAparatoTapizado(equipo, false);
  }

  private sincronizarMultiaparato(): void {
    const ids = this.modoTapizado ? this.aparatosSeleccionados.map(equipo => equipo.id) : [];
    this.parentForm.get('aparatos_ids')?.setValue(ids);
    this.parentForm.get('aparato_id')?.setValue(ids[0] ?? null);
    this.parentForm.get('detalle')?.setValue(ids.length ? `Tapizado · ${ids.length} aparatos` : null);
    this.parentForm.get('aparatos_ids')?.updateValueAndValidity();
  }

  private cargarEquiposPorSucursal(sucursalId: number) {
    // 👇 Log para depuración
    console.log('[cargarEquiposPorSucursal] sucursalId:', sucursalId, 'tipo:', this.tipo);

    this.equiposReqSub?.unsubscribe();
    this.equipos = [];
    if (!Number.isInteger(Number(sucursalId)) || Number(sucursalId) <= 0) return;
    this.equiposReqSub = this.equiposService.obtenerEquipos({ sucursal_id: sucursalId, tipo: this.tipo })
      .subscribe({
        next: resp => {
          console.log('[cargarEquiposPorSucursal] Respuesta del backend:', resp);
          this.equipos = resp || [];
        },
        error: err => {
          console.error('Error al cargar equipos:', err);
          this.equipos = [];
        }
      });
}

  get nombreTipo(): string {
    return this.tipo === 'dispositivo' ? 'Dispositivo' : 'Aparato';
  }
}
