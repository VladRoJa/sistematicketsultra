// frontend-angular/src/app/pantalla-crear-ticket/pantalla-crear-ticket.component.ts

import { Component, isDevMode, OnInit, OnDestroy } from '@angular/core';
import { HttpClient, HttpHeaders } from '@angular/common/http';
import { CommonModule } from '@angular/common';
import { Router } from '@angular/router';
import { FormBuilder, FormGroup, Validators, FormControl, ReactiveFormsModule, FormsModule } from '@angular/forms';
import { Subscription } from 'rxjs';
import { mostrarAlertaToast, mostrarAlertaErrorDesdeStatus } from '../utils/alertas';
import { environment } from 'src/environments/environment';

// Importa el formulario dinámico

// Angular Material
import { MatCardModule } from '@angular/material/card';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatSelectModule } from '@angular/material/select';
import { MatInputModule } from '@angular/material/input';
import { MatButtonModule } from '@angular/material/button';
import { FormularioDinamicoClasificacionComponent } from './formularios-crear-ticket/formulario-dinamico.component';
import { MatIcon, MatIconModule } from '@angular/material/icon';

@Component({
  selector: 'app-pantalla-crear-ticket',
  standalone: true,
  imports: [
    CommonModule,
    FormsModule,
    ReactiveFormsModule,
    FormularioDinamicoClasificacionComponent,
    MatCardModule,
    MatFormFieldModule,
    MatSelectModule,
    MatInputModule,
    MatButtonModule,
    MatIconModule
  ],
  templateUrl: './pantalla-crear-ticket.component.html',
  styleUrls: ['./pantalla-crear-ticket.component.css']
})
export class PantallaCrearTicketComponent implements OnInit, OnDestroy {

  formularioCrearTicket!: FormGroup;
  mensaje: string = '';

  departamentos = [
    { id: 1, nombre: 'Mantenimiento' },
    { id: 2, nombre: 'Finanzas' },
    { id: 3, nombre: 'Marketing' },
    { id: 4, nombre: 'Gerencia Deportiva' },
    { id: 5, nombre: 'Recursos Humanos' },
    { id: 6, nombre: 'Compras' },
    { id: 7, nombre: 'Sistemas' }
  ];

  // Para el catálogo dinámico
  clasificacionPlanoDepto: any[] = [];
  loadingClasificacion: boolean = false;
  mostrarJerarquiaDinamica = false;

  private apiUrl = `${environment.apiUrl}/tickets/create`;
  private subs: Subscription[] = [];

  constructor(
    private http: HttpClient,
    private router: Router,
    private fb: FormBuilder
  ) { }

  ngOnInit() {
    // Solo los campos globales
    this.formularioCrearTicket = this.fb.group({
      departamento: [null, Validators.required],
      tipoMantenimiento: [null],
      criticidad: [null, Validators.required],
    });

    // Limpia y prepara el formulario al cambiar departamento
    this.subs.push(
      this.formularioCrearTicket.get('departamento')!.valueChanges.subscribe(dep => {
        if (isDevMode()) console.log('[PADRE] Cambia departamento:', dep);
        this.formularioCrearTicket.patchValue({ tipoMantenimiento: null }, { emitEvent: false });
        this.resetFormularioDinamico();

        if (dep) {
          if (dep === 1) return; // Espera a seleccionar tipoMantenimiento para Mantenimiento
          this.cargarCatalogoDinamico(dep);
        } else {
          this.mostrarJerarquiaDinamica = false;
        }
      })
    );

    // Cambia tipo de mantenimiento (solo para Mantenimiento)
    this.subs.push(
      this.formularioCrearTicket.get('tipoMantenimiento')!.valueChanges.subscribe(tipo => {
        if (isDevMode()) console.log('[PADRE] Cambia tipoMantenimiento:', tipo);
        this.resetFormularioDinamico();
        if (this.formularioCrearTicket.get('departamento')?.value === 1 && tipo) {
          this.cargarCatalogoDinamico(1, tipo);
        }
      })
    );
  }

  ngOnDestroy() {
    this.subs.forEach(s => s.unsubscribe());
  }

  // Limpia todos los campos dinámicos del formulario
  resetFormularioDinamico() {
    this.mostrarJerarquiaDinamica = false;
    this.clasificacionPlanoDepto = [];
    Object.keys(this.formularioCrearTicket.controls).forEach(ctrl => {
      if (ctrl.startsWith('nivel_') || ctrl === 'descripcion') {
        this.formularioCrearTicket.removeControl(ctrl);
      }
    });
  }

  // Carga el catálogo jerárquico dinámico
  cargarCatalogoDinamico(deptoId: number, tipoMantenimiento?: string) {
    this.mostrarJerarquiaDinamica = false;
    this.loadingClasificacion = true;
    let url = `${environment.apiUrl}/catalogos/clasificaciones?departamento_id=${deptoId}`;
    // Si tienes filtros para mantenimiento, agrégalos, si no, ignóralo
    if (tipoMantenimiento) url += `&tipo_mantenimiento=${tipoMantenimiento}`;

    this.http.get<any[]>(url).subscribe({
      next: cat => {
        this.clasificacionPlanoDepto = cat;
        this.mostrarJerarquiaDinamica = true;
        this.loadingClasificacion = false;
        // Asegura que siempre exista 'descripcion'
        if (!this.formularioCrearTicket.get('descripcion')) {
          this.formularioCrearTicket.addControl('descripcion', new FormControl('', Validators.required));
        }
      },
      error: err => {
        mostrarAlertaToast('Error al cargar catálogo', 'error');
        this.loadingClasificacion = false;
        this.mostrarJerarquiaDinamica = false;
      }
    });
  }


  obtenerCamposInvalidos(form: FormGroup): string[] {
    const camposFaltantes: string[] = [];
    const nombresLegibles: { [key: string]: string } = {
      departamento: 'Departamento',
      tipoMantenimiento: 'Tipo de Mantenimiento',
      criticidad: 'Nivel de criticidad',
      descripcion: 'Descripción'
    };
    Object.keys(form.controls).forEach(campo => {
      const control = form.get(campo);
      if (control && control.invalid) {
        camposFaltantes.push(nombresLegibles[campo] || campo);
      }
    });
    return camposFaltantes;
  }

  enviarTicket() {
    if (this.formularioCrearTicket.invalid) {
      const camposFaltantes = this.obtenerCamposInvalidos(this.formularioCrearTicket);
      this.formularioCrearTicket.markAllAsTouched();
      mostrarAlertaToast(`❗Faltan datos obligatorios: ${camposFaltantes.join(', ')}`);
      return;
    }

    // Payload listo para integración con backend (puedes mapear los nivel_x si lo necesitas)
    const payload = {
      ...this.formularioCrearTicket.value,
      departamento_id: this.formularioCrearTicket.value.departamento
      // Aquí podrías mapear los valores jerárquicos si quieres mandarlos con path/nombre/id
    };
    delete payload.departamento;

    const token = localStorage.getItem('token');
    const headers = token ? new HttpHeaders().set('Authorization', `Bearer ${token}`) : new HttpHeaders();

    this.http.post<{ mensaje: string }>(this.apiUrl, payload, { headers }).subscribe({
      next: () => {
        mostrarAlertaToast('✅ Ticket creado correctamente.');
        this.formularioCrearTicket.reset();
        this.mostrarJerarquiaDinamica = false;
      },
      error: (error) => {
        mostrarAlertaErrorDesdeStatus(error.status);
      }
    });
  }

}
