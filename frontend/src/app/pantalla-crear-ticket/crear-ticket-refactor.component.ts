// frontend-angular/src/app/pantalla-crear-ticket/crear-ticket-refactor.component.ts


import { Component, OnInit, OnDestroy } from '@angular/core';
import {
  FormBuilder,
  FormGroup,
  Validators,
  FormControl,
  ReactiveFormsModule
} from '@angular/forms';
import { Subscription } from 'rxjs';
import { HttpClient, HttpHeaders } from '@angular/common/http';
import { environment } from 'src/environments/environment';
import { CatalogoService } from 'src/app/services/catalogo.service';
import {
  mostrarAlertaToast,
  mostrarAlertaErrorDesdeStatus
} from '../utils/alertas';
import { MantenimientoAparatosComponent } from './formularios-crear-ticket/mantenimiento-aparatos/mantenimiento-aparatos.component';
import { InventarioService } from 'src/app/services/inventario.service';

// 👇 Angular Material
import { CommonModule } from '@angular/common';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatSelectModule } from '@angular/material/select';
import { MatOptionModule } from '@angular/material/core';
import { MatInputModule } from '@angular/material/input';
import { MatCardModule } from '@angular/material/card';
import { MatButtonModule } from '@angular/material/button';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { SistemasComponent } from './formularios-crear-ticket/sistemas/sistemas.component';
import { SucursalesService } from '../services/sucursales.service';


import { of } from 'rxjs';
import { switchMap } from 'rxjs/operators';

@Component({
  selector: 'app-crear-ticket-refactor',
  templateUrl: './crear-ticket-refactor.component.html',
  styleUrls: ['./crear-ticket-refactor.component.css'],
  standalone: true,
  imports: [
    CommonModule,
    ReactiveFormsModule,
    MatFormFieldModule,
    MatSelectModule,
    MatOptionModule,
    MatInputModule,
    MatCardModule,
    MatButtonModule,
    MatProgressSpinnerModule,
    MantenimientoAparatosComponent,
    SistemasComponent,
  ],
})
export class CrearTicketRefactorComponent implements OnInit, OnDestroy {
  form!: FormGroup;
  niveles: {
    nivel: number;
    etiqueta: string;
    opciones: any[];
    control: FormControl;
    loading: boolean;
  }[] = [];
  subs: Subscription[] = [];
  loadingGuardar = false;
  listaSucursales: any[] = [];

  // Mapeo de nombre de control → etiqueta a mostrar
  private etiquetas: Record<string, string> = {
    sucursal_id: 'Sucursal destino',
    nivel_1:        'Departamento',
    nivel_2:        'Categoría',
    nivel_3:        'Subcategoría',
    nivel_4:        'Detalle',
    descripcion_general: 'Descripción',
    descripcion_aparato: 'Descripción del problema',
    descripcion:    'Descripción del problema',
    criticidad:    'Criticidad',
    aparato_id:     'Equipo',
    descripcion_refaccion: 'Descripción técnica de la refacción',
  };

  private readonly CATS_SISTEMAS = ['Equipo recepcion', 'Equipo gerencia', 'Uso comun'];

  private _norm(s?: string): string {
    return (s ?? '')
      .toString()
      .trim()
      .toLowerCase()
      .normalize('NFD')              // separa diacríticos
      .replace(/[\u0300-\u036f]/g, '') // quita acentos
      .replace(/\s+/g, ' ');         // colapsa espacios
  }



  constructor(
    private fb: FormBuilder,
    private http: HttpClient,
    private catalogoService: CatalogoService,
    private sucursalesService: SucursalesService,
    private inventarioService: InventarioService, 
  ) {}

  esAdmin(): boolean {
    const user = JSON.parse(localStorage.getItem('user') || '{}');
    const rol = (user.rol || '').toLowerCase().trim();
    return rol === 'administrador' || user.sucursal_id === 1000 || user.sucursal_id === 100;
  }

private limpiarRastroDeOtrosSubforms() {

  const quitar = ['categoria', 'subcategoria', 'detalle', 'descripcion'];
  quitar.forEach(c => this.form.contains(c) && this.form.removeControl(c));

  // Limpia valores colgados, pero conserva el control 'aparato_id'
  this.form.patchValue(
    {
      descripcion_general: '',
      descripcion_aparato: '',
      necesita_refaccion: false,
      aparato_id: null,           
    },
    { emitEvent: false }
  );

  // Corta niveles > 3 (los que dependen de la ruta)
  this.niveles = this.niveles.filter(n => n.nivel <= 3);
}


ngOnInit(): void {
  // Obtén la sucursal del usuario del localStorage o como corresponda
  const sucursalIdUsuario = Number(localStorage.getItem('sucursal_id')) || null;

  // Inicializa el form con sucursal_id para TODOS
  this.form = this.fb.group({
    sucursal_id: [sucursalIdUsuario, Validators.required],
    descripcion_general: [''],
    descripcion_aparato: [''],
    criticidad: [null, Validators.required],
    detalle: [''],
    subcategoria: [''],
    aparato_id: [''],
    necesita_refaccion: [false],
    descripcion_refaccion: [''],
  });

  // Si es admin, puedes permitir cambiar la sucursal y cargar lista de sucursales
  if (this.esAdmin()) {
    this.sucursalesService.obtenerSucursales().subscribe({
      next: (sucs) => (this.listaSucursales = sucs || []),
      error: (err) => console.error('Error al obtener sucursales:', err),
    });
  }

  // 3. Carga niveles iniciales
  this.cargarNivel(1, null, 'Departamento');

  const onRutaChange = () => {
  const depId = this.form.get('nivel_1')?.value;
  const catId = this.form.get('nivel_2')?.value;

  const dep = this.niveles[0]?.opciones.find(x => `${x.id}` === `${depId}`);
  const cat = this.niveles[1]?.opciones.find(x => `${x.id}` === `${catId}`);

  const esSisDisp =
    this._norm(dep?.nombre) === 'sistemas' &&
    this._norm(cat?.nombre) === 'dispositivos';

  // limpia rastro del otro flujo
  this.limpiarRastroDeOtrosSubforms();

  // si es Sistemas→Dispositivos, fuerza recargar el nivel 3 correcto
  if (esSisDisp && catId) {
    this.cargarNivel(3, catId, 'Subcategoría');
  }

  this.actualizarValidadoresDescripcion();
};

this.subs.push(this.form.get('nivel_1')!.valueChanges.subscribe(onRutaChange));
this.subs.push(this.form.get('nivel_2')!.valueChanges.subscribe(onRutaChange));

  
}


actualizarValidadoresDescripcion() {
  const general = this.form.get('descripcion_general');
  const aparato = this.form.get('descripcion_aparato');
  const sist    = this.form.get('descripcion');

  // Limpia validadores de todos
  [general, aparato, sist].forEach(ctrl => {
    if (!ctrl) return;
    ctrl.clearValidators();
  });

  if (this.mostrarSubformAparatos) {
    aparato?.setValidators([Validators.required]);
  } 
  else if (this.mostrarSubformSistemasDispositivos) {
    sist?.setValidators([Validators.required]);
  } 
  else {
    general?.setValidators([Validators.required]);
  }

  // Aplica cambios
  [general, aparato, sist].forEach(ctrl => {
    if (!ctrl) return;
    ctrl.updateValueAndValidity();
  });
}



cargarNivel(nivel: number, parentId: number | null, etiqueta: string) {
  // 1) Limpia niveles posteriores
  this.niveles = this.niveles.filter(n => n.nivel < nivel);

  // 2) Detecta la ruta actual (para decidir validadores)
  const controlName = `nivel_${nivel}`;

  const depIdSel = this.form.get('nivel_1')?.value;
  const n2IdSel  = this.form.get('nivel_2')?.value;
  const depOpt   = (this.niveles[0]?.opciones || []).find(o => `${o.id}` === `${depIdSel}`);
  const catOpt   = (this.niveles[1]?.opciones || []).find(o => `${o.id}` === `${n2IdSel}`);

  const esSistemas      = this._norm(depOpt?.nombre) === 'sistemas';
  const esDispositivos  = this._norm(catOpt?.nombre) === 'dispositivos';
  const esSisDisp       = esSistemas && esDispositivos;

  const esMantenimiento = this._norm(depOpt?.nombre) === 'mantenimiento';
  const esAparatos      = this._norm(catOpt?.nombre) === 'aparatos';
  const esMantAparatos  = esMantenimiento && esAparatos;

  // 3) Reglas de obligatoriedad por ruta/nivel
  let validators: any[] = [];
  if (nivel <= 2) {
    validators = [Validators.required];                 // nivel 1 y 2 siempre requeridos
  } else if (esSisDisp && (nivel === 3 || nivel === 4)) {
    validators = [Validators.required];                 // en Sistemas→Dispositivos, 3 y 4 requeridos
  } else if (esMantAparatos && nivel >= 3) {
    validators = [];                                    // en Mantenimiento→Aparatos, >=3 opcionales
  } else if (nivel === 5) {
    validators = [];                                    // nivel 5 opcional para cualquier ruta
  } else {
    validators = [Validators.required];                 // genérico
  }

  // 4) Crea/ajusta el control con los validadores definidos
  if (!this.form.contains(controlName)) {
    this.form.addControl(controlName, new FormControl('', validators));
  } else {
    const ctrl = this.form.get(controlName) as FormControl;
    ctrl.clearValidators();
    validators.forEach(v => ctrl.addValidators(v));
    ctrl.updateValueAndValidity({ emitEvent: false });
  }

  // 5) Registra el nivel en la UI
  this.niveles.push({
    nivel,
    etiqueta,
    opciones: [],
    control: this.form.get(controlName) as FormControl,
    loading: true,
  });

  // 6) Carga opciones
  this.catalogoService.getClasificacionesPlanas(undefined, parentId ?? undefined).subscribe({
    next: (res: any[]) => {
      const idx = this.niveles.findIndex(n => n.nivel === nivel);

      // ============================
      // NIVEL 3 especial: Sistemas → Dispositivos
      // ============================
      if (nivel === 3 && esSisDisp) {
        this.form.get('detalle')?.setValue(null, { emitEvent: false });
        this.form.get('aparato_id')?.setValue(null, { emitEvent: false });
        this.form.get('subcategoria')?.setValue(null, { emitEvent: false });

        this.inventarioService
          .listarCategoriasInventario({ nombre: 'Dispositivos', nivel: 1 })
          .pipe(
            switchMap(rows => {
              const padre = rows?.[0];
              if (!padre) return of([] as any[]);
              return this.inventarioService.listarCategoriasInventario({ parent_id: padre.id, nivel: 2 });
            })
          )
          .subscribe({
            next: (cats: any[]) => {
              const allow = new Set(this.CATS_SISTEMAS.map(this._norm)); // recepcion/gerencia/uso común
              const candidatas = (cats || []).filter(c => allow.has(this._norm(c.nombre)));

              this.niveles[idx].opciones = candidatas;
              this.niveles[idx].loading  = false;

              const ctrl3 = this.niveles[idx].control;
              if (ctrl3.value && !candidatas.some(o => `${o.id}` === `${ctrl3.value}`)) ctrl3.setValue(null);

              this.subs.push(
                ctrl3.valueChanges.subscribe(val => {
                  this.niveles = this.niveles.filter(n => n.nivel <= nivel);
                  if (val) this.cargarNivel(4, val, 'Equipo'); // nivel 4 se llena con inventario
                  this.actualizarValidadoresDescripcion();
                })
              );
            },
            error: () => {
              this.niveles[idx].opciones = [];
              this.niveles[idx].loading  = false;
            }
          });

        return; // corta el flujo genérico
      }

      // ============================
      // NIVEL 4 especial: Sistemas → Dispositivos (equipos por inventario)
      // ============================
      if (nivel === 4 && esSisDisp) {
        const catId    = this.form.get('nivel_3')?.value;
        const catObj   = (this.niveles[2]?.opciones || []).find(x => `${x.id}` === `${catId}`);
        const catNombre= catObj?.nombre || '';

        const sucursalDestino =
          this.form.value.sucursal_id ?? Number(localStorage.getItem('sucursal_id')) ?? null;

        this.inventarioService
          .obtenerInventario(sucursalDestino ? { sucursal_id: sucursalDestino } : undefined)
          .subscribe({
            next: (lista: any[]) => {
              const opciones = (lista || [])
                .filter(it => this._norm(it.categoria) === this._norm(catNombre))
                .map(it => ({
                  id: it.id,
                  nombre: `${it.nombre}${it.marca ? ' - ' + it.marca : ''}`,
                  nivel: 4,
                  nivel_nombre: 'Equipo',
                }));

              this.niveles[idx].opciones = opciones;
              this.niveles[idx].loading  = false;

              const ctrl4 = this.niveles[idx].control;
              if (ctrl4.value && !opciones.some(o => `${o.id}` === `${ctrl4.value}`)) ctrl4.setValue(null);

              this.subs.push(
                ctrl4.valueChanges.subscribe(val => {
                  this.niveles = this.niveles.filter(n => n.nivel <= nivel);
                  this.form.patchValue({ aparato_id: val });
                  this.actualizarValidadoresDescripcion();
                })
              );
            },
            error: () => {
              this.niveles[idx].opciones = [];
              this.niveles[idx].loading  = false;
            }
          });
        return; // corta aquí también
      }

      // ============================
      // Caso genérico (sin filtros especiales)
      // ============================
      this.niveles[idx].opciones =
        nivel === 1
          ? (res || []).filter(x => x.nivel === 1 || x.parent_id == null || x.parent_id === 0)
          : res;

      this.niveles[idx].loading = false;

      const ctrl = this.niveles[idx].control;
      if (ctrl.value && !this.niveles[idx].opciones.some(o => `${o.id}` === `${ctrl.value}`)) {
        ctrl.setValue(null);
      }

      this.subs.push(
        ctrl.valueChanges.subscribe(val => {
          // limpia niveles posteriores al actual
          this.niveles = this.niveles.filter(n => n.nivel <= nivel);

          if (val) {
            this.catalogoService.getClasificacionesPlanas(undefined, val).subscribe((hijos: any[]) => {
              const tieneHijos = Array.isArray(hijos) && hijos.length > 0;

              if (tieneHijos) {
                const etiquetaSig = hijos[0]?.nivel_nombre || 'Siguiente nivel';
                this.cargarNivel(nivel + 1, val, etiquetaSig);
              } else {
                // 🚫 NO hay hijos: asegúrate de no dejar nivel_(nivel+1) colgado
                const nextName = `nivel_${nivel + 1}`;
                if (this.form.contains(nextName)) this.form.removeControl(nextName);
                this.niveles = this.niveles.filter(n => n.nivel <= nivel);
              }
            });
          }

          this.actualizarValidadoresDescripcion();
        })
      );

    },
    error: () => {
      mostrarAlertaToast('Error cargando opciones', 'error');
      const idx = this.niveles.findIndex(n => n.nivel === nivel);
      if (idx >= 0) this.niveles[idx].loading = false;
    },
  });
}




  public get mostrarSubformAparatos(): boolean {
    const n1 = this.form.get('nivel_1')?.value;
    const n2 = this.form.get('nivel_2')?.value;
    const dep = this.niveles[0]?.opciones.find((x) => x.id === n1);
    const cat = this.niveles[1]?.opciones.find((x) => x.id === n2);
    return (
      dep?.nombre?.toLowerCase() === 'mantenimiento' &&
      cat?.nombre?.toLowerCase() === 'aparatos'
    );
  }

  public get mostrarSubformSistemasDispositivos(): boolean {
    const n1 = this.form.get('nivel_1')?.value;
    const n2 = this.form.get('nivel_2')?.value;

    const dep = this.niveles[0]?.opciones.find(x => x.id === n1);
    const catN2 = this.niveles[1]?.opciones.find(x => x.id === n2);

    return this._norm(dep?.nombre) === 'sistemas'
        && this._norm(catN2?.nombre) === 'dispositivos';
  }



  limpiarCamposNumericosVacios(obj: any, campos: string[]) {
    campos.forEach((c) => {
      if (obj[c] === '' || obj[c] === undefined) obj[c] = null;
    });
  }

enviar() {
  this.form.markAllAsTouched();
  const faltantes = this.getCamposInvalidos();
  if (faltantes.length) {
    mostrarAlertaToast(`Faltan campos obligatorios: ${faltantes.join(', ')}`, 'error');
    return;
  }

  // --- ids seleccionados por nivel ---
  const n1 = this.form.get('nivel_1')?.value; // Departamento
  const n2 = this.form.get('nivel_2')?.value; // Categoría (p.ej. Dispositivos)
  const n3 = this.form.get('nivel_3')?.value; // Subcategoría (Equipo recepción/gerencia/uso común)
  const n4 = this.form.get('nivel_4')?.value; // Equipo (inventario.id) en Sistemas→Dispositivos

  // --- departamento_id real desde el nivel 1 ---
  const depObj = this.niveles[0]?.opciones.find(o => o.id === n1);
  const departamento_id = depObj?.departamento_id;

  // ¿Estamos en el camino Sistemas → Dispositivos?
  const depName = (depObj?.nombre || '').trim().toUpperCase();
  const n2Obj = this.niveles[1]?.opciones.find(o => o.id === n2);
  const n2Name = (n2Obj?.nombre || '').trim().toUpperCase();
  const esSisDisp = depName === 'SISTEMAS' && n2Name === 'DISPOSITIVOS';

  // --- clasificacion_id: último nodo de CLASIFICACIÓN (no el equipo) ---
  let clasificacion_id: number | null = null;
  if (esSisDisp) {
    // En Sistemas→Dispositivos el último nodo de clasificación es el nivel 3 (subcategoría)
    clasificacion_id = n3 ?? n2 ?? n1 ?? null;
  } else {
    // Flujo genérico: toma el último nivel elegido
    for (let i = this.niveles.length - 1; i >= 0; i--) {
      const val = this.form.get(`nivel_${this.niveles[i].nivel}`)?.value;
      if (val) { clasificacion_id = val; break; }
    }
  }

  // --- descripción final según subform activo ---
  const descripcionFinal =
    this.mostrarSubformAparatos
      ? this.form.value.descripcion_aparato
      : this.mostrarSubformSistemasDispositivos
        ? this.form.value.descripcion
        : this.form.value.descripcion_general;

  // --- sucursal destino (admin elige; usuario toma su sucursal del localStorage) ---
  const sucursalDestino = this.form.value.sucursal_id ?? Number(localStorage.getItem('sucursal_id'));

  // --- construir body (sin 'detalle' de entrada) ---
  const body: any = {
    sucursal_id_destino: sucursalDestino,
    descripcion: descripcionFinal,
    criticidad: this.form.value.criticidad,
    departamento_id,
    categoria: n2 ?? null,
    subcategoria: n3 ?? null,
    clasificacion_id,
    aparato_id: esSisDisp ? n4 : (this.form.value.aparato_id ?? null),
    necesita_refaccion: this.form.value.necesita_refaccion,
    descripcion_refaccion: this.form.value.descripcion_refaccion,
  };

  // 'detalle' SOLO cuando NO es Sistemas → Dispositivos
  if (!esSisDisp) {
    body.detalle = this.form.get('nivel_4')?.value ?? null;
  } else {
    // blindaje: si algún subform dejó algo en 'detalle', lo limpiamos
    this.form.get('detalle')?.reset(null, { emitEvent: false });
    delete body.detalle;
  }

  console.log('BODY ENVIADO:', body);

  const token = localStorage.getItem('token');
  const headers = token ? new HttpHeaders().set('Authorization', `Bearer ${token}`) : undefined;
  this.loadingGuardar = true;

  // LIMPIEZA de numéricos opcionales (sin 'detalle')
  this.limpiarCamposNumericosVacios(body, [
    'aparato_id',
    'clasificacion_id',
    'categoria',
    'subcategoria',
  ]);

  // doble seguro: en el flujo Sistemas→Dispositivos no debe existir 'detalle'
  if (esSisDisp && 'detalle' in body) delete body.detalle;


  this.http.post<{ mensaje: string }>(`${environment.apiUrl}/tickets/create`, body, { headers }).subscribe({
    next: () => {
      mostrarAlertaToast('✅ Ticket creado correctamente');
      this.form.reset();
      this.niveles = [];
      this.cargarNivel(1, null, 'Departamento');
      this.loadingGuardar = false;
    },
    error: (err) => {
      mostrarAlertaErrorDesdeStatus(err.status);
      this.loadingGuardar = false;
    }
  });
}


getCamposInvalidos(): string[] {
  const faltan: string[] = [];
  Object.entries(this.form.controls).forEach(([key, ctrl]) => {
    if (ctrl.invalid && ctrl.errors?.['required']) {
      // ⚡️ Aquí agregamos la condición para sucursal_id
      if (
        key === 'sucursal_id' &&
        !this.esAdmin()
      ) {
        // Si no es admin, ignoramos el error de sucursal_id
        return;
      }
      // Solo agrega si corresponde al subform activo
      if (
        (key === 'descripcion' && this.mostrarSubformSistemasDispositivos) ||
        (key === 'descripcion_aparato' && this.mostrarSubformAparatos) ||
        (key === 'descripcion_general' && !this.mostrarSubformAparatos && !this.mostrarSubformSistemasDispositivos) ||
        !['descripcion', 'descripcion_aparato', 'descripcion_general'].includes(key)
      ) {
        const label = this.etiquetas[key] || key;
        if (!faltan.includes(label)) faltan.push(label);
      }
    }
  });
  return faltan;
}


    /**
   * Este método se dispara cuando <app-sistemas> emite formularioValido.
   * @param payload El objeto que envía el subformulario de Sistemas
   */
onFormularioSistemasValido(payload: any) {
  // 1) Asegura el control una sola vez
  if (!this.form.contains('descripcion')) {
    this.form.addControl('descripcion', new FormControl('', Validators.required));
  }

  // 2) Solo actualizar si cambió
  const ctrl = this.form.get('descripcion') as FormControl;
  const nuevoValor = payload?.descripcion || '';

  if (ctrl.value !== nuevoValor) {
    // 3) No dispares valueChanges al subform otra vez
    ctrl.setValue(nuevoValor, { emitEvent: false });
  }
}





  ngOnDestroy(): void {
    this.subs.forEach((s) => s.unsubscribe());
  }


  
}

