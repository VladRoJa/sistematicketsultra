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

  constructor(
    private fb: FormBuilder,
    private http: HttpClient,
    private catalogoService: CatalogoService,
    private sucursalesService: SucursalesService
  ) {}

  esAdmin(): boolean {
    const user = JSON.parse(localStorage.getItem('user') || '{}');
    const rol = (user.rol || '').toLowerCase().trim();
    return rol === 'administrador' || user.sucursal_id === 1000;
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
    this.niveles = this.niveles.filter((n) => n.nivel < nivel);
    const controlName = `nivel_${nivel}`;
    if (!this.form.contains(controlName)) {
      this.form.addControl(
        controlName,
        new FormControl('', Validators.required)
      );
    }
    this.niveles.push({
      nivel,
      etiqueta,
      opciones: [],
      control: this.form.get(controlName) as FormControl,
      loading: true,
    });

    this.catalogoService
      .getClasificacionesPlanas(undefined, parentId ?? undefined)
      .subscribe({
        next: (res: any[]) => {
          const idx = this.niveles.findIndex((n) => n.nivel === nivel);
          this.niveles[idx].opciones =
            nivel === 1
              ? res.filter(
                  (x) => x.nivel === 1 || x.parent_id == null || x.parent_id === 0
                )
              : res;
          this.niveles[idx].loading = false;
          this.subs.push(
            this.niveles[idx].control.valueChanges.subscribe((val) => {
              this.niveles = this.niveles.filter((n) => n.nivel <= nivel);
              if (val) {
                this.catalogoService
                  .getClasificacionesPlanas(undefined, val)
                  .subscribe((hijos: any[]) => {
                    if (hijos.length) {
                      this.cargarNivel(
                        nivel + 1,
                        val,
                        hijos[0].nivel_nombre || 'Siguiente nivel'
                      );
                    }
                  });
              }
              this.actualizarValidadoresDescripcion();
            })
          );
        },
            error: () => {
      mostrarAlertaToast('Error cargando opciones', 'error');
      const idx = this.niveles.findIndex((n) => n.nivel === nivel);
      if (idx >= 0) this.niveles[idx].loading = false; // apaga loader en error
    }
        

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
    const dep = this.niveles[0]?.opciones.find((x) => x.id === n1);
    const cat = this.niveles[1]?.opciones.find((x) => x.id === n2);
    return (
      dep?.nombre?.toLowerCase() === 'sistemas' &&
      cat?.nombre?.toLowerCase() === 'dispositivos'
    );
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
      mostrarAlertaToast(
        `Faltan campos obligatorios: ${faltantes.join(', ')}`,
        'error'
      );
      return;
    }

  // --- Obtén los ids seleccionados en cada nivel ---
  const nivel_1_id = this.form.get('nivel_1')?.value; // id de la primera clasificación (no es forzosamente el departamento)
  const categoria = this.form.get('nivel_2')?.value;
  const subcategoria = this.form.get('nivel_3')?.value;
  const detalle = this.form.get('nivel_4')?.value;

  // --- Busca el objeto seleccionado en el primer nivel para sacar su departamento_id real ---
  const primerNivelSeleccionado = this.niveles[0]?.opciones.find(opt => opt.id === nivel_1_id);
  const departamento_id = primerNivelSeleccionado?.departamento_id; // este sí es el FK de la tabla departamentos

  // --- Saca el último nivel como clasificacion_id ---
  let clasificacion_id: number | null = null;
  for (let i = this.niveles.length - 1; i >= 0; i--) {
    const val = this.form.get(`nivel_${this.niveles[i].nivel}`)?.value;
    if (val) {
      clasificacion_id = val;
      break;
    }
  }

   const descripcionFinal =
    this.mostrarSubformAparatos
      ? this.form.value.descripcion_aparato
      : this.mostrarSubformSistemasDispositivos
        ? this.form.value.descripcion
        : this.form.value.descripcion_general;

    const body = {
      descripcion: descripcionFinal,
      criticidad: this.form.value.criticidad,
      departamento_id,
      categoria,
      subcategoria,
      detalle,
      clasificacion_id,
      aparato_id: this.form.value.aparato_id, 
      necesita_refaccion: this.form.value.necesita_refaccion,        
      descripcion_refaccion: this.form.value.descripcion_refaccion, 
    };

  console.log('BODY ENVIADO:', body);

  const token = localStorage.getItem('token');
  const headers = token ? new HttpHeaders().set('Authorization', `Bearer ${token}`) : undefined;
  this.loadingGuardar = true;
  
  // LIMPIEZA de campos numéricos opcionales:
  this.limpiarCamposNumericosVacios(body, [
    'aparato_id',
    'clasificacion_id',
    'categoria',
    'subcategoria',
    'detalle'
  ]);


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
  console.log('Formulario de Sistemas válido:', payload);

  // 1. Asegura que el form tenga el campo 'descripcion'
  if (!this.form.contains('descripcion')) {
    this.form.addControl('descripcion', new FormControl('', Validators.required));
  }

  // 2. Pone el valor de la descripción recibida desde el subform
  this.form.patchValue({
    descripcion: payload.descripcion || ''
  });
}




  ngOnDestroy(): void {
    this.subs.forEach((s) => s.unsubscribe());
  }
}

