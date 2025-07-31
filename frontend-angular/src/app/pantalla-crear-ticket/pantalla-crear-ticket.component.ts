// frontend-angular/src/app/pantalla-crear-ticket/pantalla-crear-ticket.component.ts

import { Component, OnInit, OnDestroy, ChangeDetectorRef } from '@angular/core';
import { FormBuilder, FormGroup, ReactiveFormsModule, Validators } from '@angular/forms';
import { Subscription } from 'rxjs';
import { CatalogoService } from 'src/app/services/catalogo.service'; // importa tu servicio plano
import { mostrarAlertaToast, mostrarAlertaErrorDesdeStatus } from '../utils/alertas';
import { HttpClient, HttpHeaders } from '@angular/common/http';
import { environment } from 'src/environments/environment';
import { MatIconModule } from '@angular/material/icon';
import { MatButtonModule } from '@angular/material/button';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatSelectModule } from '@angular/material/select';
import { MatInputModule } from '@angular/material/input';
import { MatCardModule } from '@angular/material/card';
import { JsonPipe } from '@angular/common';


@Component({
  selector: 'app-pantalla-crear-ticket',
  templateUrl: './pantalla-crear-ticket.component.html',
  styleUrls: ['./pantalla-crear-ticket.component.css'],
  standalone: true,
  imports: [
    MatIconModule,
    MatButtonModule,
    MatFormFieldModule,
    MatSelectModule,
    MatInputModule,
    MatCardModule,
    ReactiveFormsModule,
    JsonPipe
],
})
export class PantallaCrearTicketComponent implements OnInit, OnDestroy {

  formularioCrearTicket!: FormGroup;

  public departamentos: any[] = [];
  categorias: any[] = [];
  subcategorias: any[] = [];
  detalles: any[] = [];
  nivelesCriticidad = [1, 2, 3, 4, 5];
  departamentosDummy = [
  { departamento_id: 1, nombre: 'Admin', nivel: 1 },
  { departamento_id: 2, nombre: 'Ventas', nivel: 1 },
  { departamento_id: 3, nombre: 'Soporte', nivel: 1 }
];

  loading = false;
  subs: Subscription[] = [];

  constructor(
    private catalogoService: CatalogoService,
    private fb: FormBuilder,
    private http: HttpClient,
    private cdr: ChangeDetectorRef,
  ) {}

  ngOnInit() {
    this.formularioCrearTicket = this.fb.group({
      departamento: [[''], Validators.required],
      categoria: [null, Validators.required],
      subcategoria: [null, Validators.required],
      detalle: [null, Validators.required],
      criticidad: [null, Validators.required],
      descripcion: ['', Validators.required]
    });

    // Cargar departamentos raíz (nivel 1, sin parent)
this.catalogoService.getClasificacionesPlanas().subscribe({
  next: res => {
    this.departamentos = res.filter((n: any) => n.nivel === 1 && (n.parent_id === null || n.parent_id === 0));
    console.log('Departamentos raizzzz:', this.departamentos);
    this.cdr.detectChanges(); // <--- ¡Fuerza el render aquí!
  },
  error: err => mostrarAlertaToast('Error al cargar departamentos', 'error')
});
    // Cuando cambia departamento, cargar categorías hijas (nivel 2)
    this.subs.push(
      this.formularioCrearTicket.get('departamento')!.valueChanges.subscribe(idDepto => {
        this.categorias = [];
        this.subcategorias = [];
        this.detalles = [];
        this.formularioCrearTicket.patchValue({ categoria: null, subcategoria: null, detalle: null });

        if (!idDepto) return;
        this.catalogoService.getClasificacionesPlanas(undefined, idDepto).subscribe({
          next: res => { this.categorias = res; },
          error: err => mostrarAlertaToast('Error al cargar categorías', 'error')
        });
      })
    );

    // Cuando cambia categoría, cargar subcategorías (nivel 3)
    this.subs.push(
      this.formularioCrearTicket.get('categoria')!.valueChanges.subscribe(idCat => {
        this.subcategorias = [];
        this.detalles = [];
        this.formularioCrearTicket.patchValue({ subcategoria: null, detalle: null });

        if (!idCat) return;
        this.catalogoService.getClasificacionesPlanas(undefined, idCat).subscribe({
          next: res => { this.subcategorias = res; },
          error: err => mostrarAlertaToast('Error al cargar subcategorías', 'error')
        });
      })
    );

    // Cuando cambia subcategoría, cargar detalles (nivel 4)
    this.subs.push(
      this.formularioCrearTicket.get('subcategoria')!.valueChanges.subscribe(idSub => {
        this.detalles = [];
        this.formularioCrearTicket.patchValue({ detalle: null });

        if (!idSub) return;
        this.catalogoService.getClasificacionesPlanas(undefined, idSub).subscribe({
          next: res => { this.detalles = res; },
          error: err => mostrarAlertaToast('Error al cargar detalles', 'error')
        });
      })
    );
  }

  ngOnDestroy() {
    this.subs.forEach(s => s.unsubscribe());
  }

  enviarTicket() {
    if (this.formularioCrearTicket.invalid) {
      this.formularioCrearTicket.markAllAsTouched();
      mostrarAlertaToast('Faltan datos obligatorios');
      return;
    }
    // Ajusta aquí tu payload si necesitas otro id
    const payload = { ...this.formularioCrearTicket.value };

    const token = localStorage.getItem('token');
    const headers = token ? new HttpHeaders().set('Authorization', `Bearer ${token}`) : new HttpHeaders();

    this.loading = true;
    // Cambia aquí si necesitas enviar a otro endpoint
    this.http.post<{ mensaje: string }>(`${environment.apiUrl}/tickets/create`, payload, { headers }).subscribe({
      next: () => {
        mostrarAlertaToast('✅ Ticket creado correctamente.');
        this.formularioCrearTicket.reset();
        this.categorias = [];
        this.subcategorias = [];
        this.detalles = [];
        this.loading = false;
      },
      error: (error) => {
        mostrarAlertaErrorDesdeStatus(error.status);
        this.loading = false;
      }
    });
  }

}

