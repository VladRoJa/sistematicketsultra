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

  private onRutaChangeFn?: () => void;
  private hookedNivel2 = false;
  private nivel2Sub?: Subscription;
  private reqTokenByNivel: Record<number, number> = {};
  private readonly ID_CAT_DISPOSITIVOS = 2;
  trackByNivel = (_: number, n: { nivel: number }) => n.nivel;




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
  // 1) Sucursal por defecto (del usuario)
  const sucursalIdUsuario = Number(localStorage.getItem('sucursal_id')) || null;

  // 2) Form principal
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

  // 3) Si es admin, carga catálogo de sucursales
  if (this.esAdmin()) {
    this.sucursalesService.obtenerSucursales().subscribe({
      next: (sucs) => (this.listaSucursales = sucs || []),
      error: (err) => console.error('Error al obtener sucursales:', err),
    });
  }

  // 4) Handler para cambios de ruta (Departamento/Categoría)
  this.onRutaChangeFn = () => {

    console.debug('[onRutaChange]', {
  n1: this.form.get('nivel_1')?.value,
  n2: this.form.get('nivel_2')?.value,
  esSisDisp: this.mostrarSubformSistemasDispositivos
});
    const depId = this.form.get('nivel_1')?.value;
    const catId = this.form.get('nivel_2')?.value;

    const dep = this.niveles[0]?.opciones.find(x => `${x.id}` === `${depId}`);
    const cat = this.niveles[1]?.opciones.find(x => `${x.id}` === `${catId}`);

    const esSisDisp =
      this._norm(dep?.nombre) === 'sistemas' &&
      this._norm(cat?.nombre) === 'dispositivos';

    // Limpia rastro del otro flujo
    this.limpiarRastroDeOtrosSubforms();

    // Si es Sistemas→Dispositivos, forzar recarga del nivel 3 correcto
    if (esSisDisp && catId) {
      this.cargarNivel(3, catId, 'Subcategoría');
    }

    this.actualizarValidadoresDescripcion();
  };

  // 5) Cargar nivel 1 (crea control nivel_1)
  this.cargarNivel(1, null, 'Departamento');

  // 6) Suscripción segura a nivel_1 (el control ya existe)
  const c1 = this.form.get('nivel_1') as FormControl | null;
  if (c1) {
this.subs.push(c1.valueChanges.subscribe(() => this.onRutaChangeFn?.()));
  }

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

  // 2) Ruta actual
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

  console.debug('[cargarNivel] nivel:', nivel, 'parentId:', parentId, 'etiqueta:', etiqueta, 'esSisDisp:', esSisDisp);

  // 3) Validadores por nivel/ruta
  let validators: any[] = [];
  if (nivel <= 2) validators = [Validators.required];
  else if (esSisDisp && (nivel === 3 || nivel === 4)) validators = [Validators.required];
  else if (esMantAparatos && nivel >= 3) validators = [];
  else if (nivel === 5) validators = [];
  else validators = [Validators.required];

  // 4) Crea/ajusta control
  if (!this.form.contains(controlName)) {
    this.form.addControl(controlName, new FormControl('', validators));
  } else {
    const ctrl = this.form.get(controlName) as FormControl;
    ctrl.clearValidators();
    validators.forEach(v => ctrl.addValidators(v));
    ctrl.updateValueAndValidity({ emitEvent: false });
  }

  // 5) Registra el nivel en UI
  this.niveles.push({
    nivel,
    etiqueta,
    opciones: [],
    control: this.form.get(controlName) as FormControl,
    loading: true,
  });

  // Hook onRutaChange a nivel_2 (solo una vez)
  if (nivel === 2 && !this.hookedNivel2 && this.onRutaChangeFn) {
    const c2 = this.form.get('nivel_2') as FormControl;
    if (c2) {
      this.nivel2Sub?.unsubscribe();
      this.nivel2Sub = c2.valueChanges.subscribe(() => this.onRutaChangeFn?.());
      this.hookedNivel2 = true;
    }
  }

  // token anti race
  const token = (this.reqTokenByNivel[nivel] || 0) + 1;
  this.reqTokenByNivel[nivel] = token;

  // ============================
  // 🔴 RAMA ESPECIAL *ANTES* del catálogo plano
  // ============================

  // NIVEL 3: categorías de inventario hijas de "Dispositivos" (id=2 en catalogo_categoria_inventario)
  if (nivel === 3 && esSisDisp) {
    const fila3 = this.niveles.find(n => n.nivel === 3);
    if (!fila3) return;

    const padreIdInventario = 2; // "Dispositivos" en catalogo_categoria_inventario
    console.debug('[N3] Listando categorías de inventario parent_id=', padreIdInventario);

    this.inventarioService.listarCategoriasInventario({ parent_id: padreIdInventario }).subscribe({
      next: (cats: any[]) => {
        if (token !== this.reqTokenByNivel[nivel]) return;
        fila3.opciones = cats || [];
        fila3.loading  = false;

        const ctrl3 = fila3.control;
        if (ctrl3.value && !fila3.opciones.some(o => `${o.id}` === `${ctrl3.value}`)) ctrl3.setValue(null);

        this.subs.push(
          ctrl3.valueChanges.subscribe(val => {
            this.niveles = this.niveles.filter(n => n.nivel <= nivel);
            if (val) this.cargarNivel(4, val, 'Equipo'); // Nivel 4: inventario por categoría
            this.actualizarValidadoresDescripcion();
          })
        );
      },
      error: (e) => {
        console.error('[N3] Error categorías inventario:', e);
        fila3.opciones = [];
        fila3.loading  = false;
      }
    });
    return; // 🔚 no llames al catálogo plano
  }

  // NIVEL 4: equipos del inventario por categoría y sucursal
  if (nivel === 4 && esSisDisp) {
    const fila4 = this.niveles.find(n => n.nivel === 4);
    if (!fila4) return;

    const catId = this.form.get('nivel_3')?.value as number | null;
    const sucursalDestino = this.form.value.sucursal_id ?? Number(localStorage.getItem('sucursal_id')) ?? undefined;

    console.debug('[N4] Listando inventario por categoría=', catId, 'sucursal=', sucursalDestino);

    this.inventarioService.listarInventarioPorCategoriaYSucursal({
      categoria_inventario_id: Number(catId),
      sucursal_id: sucursalDestino,
    }).subscribe({
      next: (items: any[]) => {
        if (token !== this.reqTokenByNivel[nivel]) return;
        fila4.opciones = (items || []).map(it => ({
          id: it.id,
          nombre: `${it.nombre}${it.marca ? ' - ' + it.marca : ''}`,
          nivel: 4,
          nivel_nombre: 'Equipo',
        }));
        fila4.loading  = false;

        const ctrl4 = fila4.control;
        if (ctrl4.value && !fila4.opciones.some(o => `${o.id}` === `${ctrl4.value}`)) ctrl4.setValue(null);

        this.subs.push(
          ctrl4.valueChanges.subscribe(val => {
            this.niveles = this.niveles.filter(n => n.nivel <= nivel);
            this.form.patchValue({ aparato_id: val });
            this.actualizarValidadoresDescripcion();
          })
        );
      },
      error: (e) => {
        console.error('[N4] Error inventario por categoría:', e);
        fila4.opciones = [];
        fila4.loading  = false;
      }
    });
    return; // 🔚 no llames al catálogo plano
  }

  // ============================
  // Caso genérico (catálogo plano)
  // ============================
  this.catalogoService.getClasificacionesPlanas(undefined, parentId ?? undefined).subscribe({
    next: (res: any[]) => {
      if (token !== this.reqTokenByNivel[nivel]) return;
      const fila = this.niveles.find(n => n.nivel === nivel);
      if (!fila) return;

      fila.opciones = nivel === 1
        ? (res || []).filter(x => x.nivel === 1 || x.parent_id == null || x.parent_id === 0)
        : (res || []);

      fila.loading = false;

      const ctrl = fila.control;
      if (ctrl.value && !fila.opciones.some(o => `${o.id}` === `${ctrl.value}`)) ctrl.setValue(null);

this.subs.push(
  ctrl.valueChanges.subscribe(val => {
    // 👇 calcula si estás en Sistemas→Dispositivos
    const depSel = this.niveles[0]?.opciones.find(o => `${o.id}` === `${this.form.get('nivel_1')?.value}`);
    const catSel = this.niveles[1]?.opciones.find(o => `${o.id}` === `${this.form.get('nivel_2')?.value}`);
    const _esSisDisp = this._norm(depSel?.nombre) === 'sistemas' && this._norm(catSel?.nombre) === 'dispositivos';

    // ⛔️ Si es Sistemas→Dispositivos, NO limpies ni generes hijos aquí.
    // Deja que onRutaChange() maneje el nivel 3 especial.
    if (nivel === 2 && _esSisDisp) {
      this.actualizarValidadoresDescripcion();
      return;
    }

    // ✅ Fuera de la rama especial, ahora sí limpia y genera hijos normales
    this.niveles = this.niveles.filter(n => n.nivel <= nivel);

    if (val) {
      this.catalogoService.getClasificacionesPlanas(undefined, val).subscribe((hijos: any[]) => {
        const tieneHijos = Array.isArray(hijos) && hijos.length > 0;
        if (tieneHijos && nivel < 5) {
          const etiquetaSig = hijos[0]?.nivel_nombre || 'Siguiente nivel';
          this.cargarNivel(nivel + 1, val, etiquetaSig);
        } else {
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
    error: (e) => {
      if (token !== this.reqTokenByNivel[nivel]) return;
      const fila = this.niveles.find(n => n.nivel === nivel);
      if (!fila) return;
      console.error('[Gen] Error catálogo clasificaciones:', e);
      mostrarAlertaToast('Error cargando opciones', 'error');
      fila.loading = false;
    },
  });
}




public get mostrarSubformAparatos(): boolean {
  const n1 = this.form.get('nivel_1')?.value;
  const n2 = this.form.get('nivel_2')?.value;
  const dep = this.niveles[0]?.opciones.find(x => `${x.id}` === `${n1}`);
  const cat = this.niveles[1]?.opciones.find(x => `${x.id}` === `${n2}`);
  return this._norm(dep?.nombre) === 'mantenimiento'
      && this._norm(cat?.nombre) === 'aparatos';
}

public get mostrarSubformSistemasDispositivos(): boolean {
  const n1 = this.form.get('nivel_1')?.value;
  const n2 = this.form.get('nivel_2')?.value;
  const dep   = this.niveles[0]?.opciones.find(x => `${x.id}` === `${n1}`);
  const catN2 = this.niveles[1]?.opciones.find(x => `${x.id}` === `${n2}`);
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
      this.form.reset({
        sucursal_id: Number(localStorage.getItem('sucursal_id')) || null,
        criticidad: null
      });
      this.nivel2Sub?.unsubscribe();  
      this.nivel2Sub = undefined;
      this.niveles = [];
      this.hookedNivel2 = false;
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
      this.nivel2Sub?.unsubscribe(); // ← agrega esto
    }


  
}

