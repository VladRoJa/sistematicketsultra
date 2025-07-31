// frontend-angular/src/app/pantalla-crear-ticket/crear-ticket-refactor.component.ts

import { Component, OnInit, OnDestroy } from '@angular/core';
import { FormBuilder, FormGroup, Validators, FormControl, ReactiveFormsModule } from '@angular/forms';
import { Subscription } from 'rxjs';
import { HttpClient, HttpHeaders } from '@angular/common/http';
import { environment } from 'src/environments/environment';
import { CatalogoService } from 'src/app/services/catalogo.service';
import { mostrarAlertaToast, mostrarAlertaErrorDesdeStatus } from '../utils/alertas';

// 👇 Angular Material
import { CommonModule } from '@angular/common';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatSelectModule } from '@angular/material/select';
import { MatOptionModule } from '@angular/material/core';
import { MatInputModule } from '@angular/material/input';
import { MatCardModule } from '@angular/material/card';
import { MatButtonModule } from '@angular/material/button';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';

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
    MatProgressSpinnerModule
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

  constructor(
    private fb: FormBuilder,
    private http: HttpClient,
    private catalogoService: CatalogoService
  ) {}

  ngOnInit(): void {
    // Inicializa el form antes de los niveles
    this.form = this.fb.group({
      descripcion: ['', Validators.required],
      criticidad: [null, Validators.required]
    });
    // Inicia el árbol en nivel 1 (solo departamentos root, parent_id: null)
    this.cargarNivel(1, null, 'Departamento');
  }

 cargarNivel(nivel: number, parentId: number | null, etiqueta: string) {
  // Borra los niveles siguientes si eligen otro padre
  this.niveles = this.niveles.filter(n => n.nivel < nivel);

  const controlName = `nivel_${nivel}`;
  // Solo agrega control si no existe
  if (!this.form.contains(controlName)) {
    this.form.addControl(controlName, new FormControl('', Validators.required));
  }

  // Añade el nivel con loading
  this.niveles.push({
    nivel,
    etiqueta,
    opciones: [],
    control: this.form.get(controlName) as FormControl,
    loading: true
  });

  // Trae las opciones del nivel correspondiente
  this.catalogoService.getClasificacionesPlanas(undefined, parentId ?? undefined).subscribe({
    next: (res: any[]) => {
      const idx = this.niveles.findIndex(n => n.nivel === nivel);

      // Si es el primer nivel (departamento), filtra solo los nodos de nivel 1 (y sin padre)
      this.niveles[idx].opciones = (nivel === 1)
        ? res.filter(x => x.nivel === 1 || x.parent_id == null || x.parent_id === 0)
        : res;
      this.niveles[idx].loading = false;

      // Suscribe cambios (sin usar observers)
      this.subs.push(
        this.niveles[idx].control.valueChanges.subscribe(val => {
          // Borra niveles posteriores
          this.niveles = this.niveles.filter(n => n.nivel <= nivel);
          // Si selecciona, trae hijos si existen
          if (val) {
            this.catalogoService.getClasificacionesPlanas(undefined, val).subscribe((hijos: any[]) => {
              if (hijos.length) {
                this.cargarNivel(nivel + 1, val, hijos[0].nivel_nombre || 'Siguiente nivel');
              }
            });
          }
        })
      );
    },
    error: () => mostrarAlertaToast('Error cargando opciones', 'error')
  });
}


enviar() {
  if (this.form.invalid) {
    this.form.markAllAsTouched();
    mostrarAlertaToast('Faltan campos obligatorios');
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

  const body = {
    descripcion: this.form.value.descripcion,
    criticidad: this.form.value.criticidad,
    departamento_id,  // <-- ahora sí es el que pide la FK
    categoria,
    subcategoria,
    detalle,
    clasificacion_id,
  };

  console.log('BODY ENVIADO:', body);

  const token = localStorage.getItem('token');
  const headers = token ? new HttpHeaders().set('Authorization', `Bearer ${token}`) : undefined;
  this.loadingGuardar = true;
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



  ngOnDestroy(): void {
    this.subs.forEach(s => s.unsubscribe());
  }
}
