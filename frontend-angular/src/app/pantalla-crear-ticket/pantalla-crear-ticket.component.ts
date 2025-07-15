// frontend-angular\src\app\pantalla-crear-ticket\pantalla-crear-ticket.component.ts

import { Component, OnInit } from '@angular/core';
import { HttpClient, HttpHeaders } from '@angular/common/http';
import { CommonModule } from '@angular/common';
import { Router } from '@angular/router';
import { FormBuilder, FormGroup, ReactiveFormsModule, FormsModule, Validators } from '@angular/forms';
import { mostrarAlertaToast, mostrarAlertaErrorDesdeStatus } from '../utils/alertas';
import { environment } from 'src/environments/environment';

// IMPORTS de los subformularios
import { MantenimientoAparatosComponent } from './formularios-crear-ticket/mantenimiento-aparatos/mantenimiento-aparatos.component';
import { MantenimientoEdificioComponent } from './formularios-crear-ticket/mantenimiento-edificio/mantenimiento-edificio.component';
import { FinanzasComponent } from './formularios-crear-ticket/finanzas/finanzas.component';
import { MarketingComponent } from './formularios-crear-ticket/marketing/marketing.component';
import { GerenciaDeportivaComponent } from './formularios-crear-ticket/gerencia-deportiva/gerencia-deportiva.component';
import { RecursosHumanosComponent } from './formularios-crear-ticket/recursos-humanos/recursos-humanos.component';
import { ComprasComponent } from './formularios-crear-ticket/compras/compras.component';
import { SistemasComponent } from './formularios-crear-ticket/sistemas/sistemas.component';

// Angular Material
import { MatCardModule } from '@angular/material/card';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatSelectModule } from '@angular/material/select';
import { MatInputModule } from '@angular/material/input';
import { MatButtonModule } from '@angular/material/button';

@Component({
  selector: 'app-pantalla-crear-ticket',
  standalone: true,
  imports: [
    CommonModule,
    FormsModule,
    ReactiveFormsModule,
    MantenimientoEdificioComponent,
    MantenimientoAparatosComponent,
    FinanzasComponent,
    MarketingComponent,
    GerenciaDeportivaComponent,
    RecursosHumanosComponent,
    ComprasComponent,
    SistemasComponent,
    MatCardModule,
    MatFormFieldModule,
    MatSelectModule,
    MatInputModule,
    MatButtonModule
  ],
  templateUrl: './pantalla-crear-ticket.component.html',
  styleUrls: ['./pantalla-crear-ticket.component.css']
})
export class PantallaCrearTicketComponent implements OnInit {

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

  private apiUrl = `${environment.apiUrl}/tickets/create`;

  constructor(
    private http: HttpClient,
    private router: Router,
    private fb: FormBuilder
  ) { }

  ngOnInit() {
    this.formularioCrearTicket = this.fb.group({
      departamento: [null, Validators.required],
      tipoMantenimiento: [null],
      categoria: ['', Validators.required],
      subcategoria: ['', Validators.required],
      detalle: ['', Validators.required],
      descripcion: ['', Validators.required],
      criticidad: [null, Validators.required],
      necesita_refaccion: [false],
      descripcion_refaccion: ['']
    });

    this.formularioCrearTicket.get('departamento')?.valueChanges.subscribe(() => {
      this.formularioCrearTicket.patchValue({ tipoMantenimiento: null });
    });

    this.formularioCrearTicket.get('tipoMantenimiento')?.valueChanges.subscribe(() => {
      this.resetCamposTipo();
    });
  }

  resetCamposTipo() {
    const keysAEliminar = [
      'aparato_id',
      'problema_detectado',
      'necesita_refaccion',
      'descripcion_refaccion'
    ];

    keysAEliminar.forEach(campo => {
      if (this.formularioCrearTicket.contains(campo)) {
        this.formularioCrearTicket.removeControl(campo);
      }
    });
  }

  obtenerCamposInvalidos(form: FormGroup): string[] {
    const camposFaltantes: string[] = [];

    const nombresLegibles: { [key: string]: string } = {
      departamento: 'Departamento',
      tipoMantenimiento: 'Tipo de Mantenimiento',
      categoria: 'Categoría',
      subcategoria: 'Subcategoría',
      detalle: 'Detalle específico',
      descripcion: 'Descripción',
      criticidad: 'Nivel de criticidad'
    };

    Object.keys(form.controls).forEach(campo => {
      const control = form.get(campo);
      if (control && control.invalid) {
        camposFaltantes.push(nombresLegibles[campo] || campo);
      }
    });

    return camposFaltantes;
  }

  formatearNombreCampo(campo: string): string {
    const traducciones: Record<string, string> = {
      departamento: 'Departamento',
      tipoMantenimiento: 'Tipo de Mantenimiento',
      categoria: 'Categoría',
      subcategoria: 'Subcategoría',
      detalle: 'Detalle',
      descripcion: 'Descripción',
      criticidad: 'Nivel de criticidad'
    };

    return traducciones[campo] || campo;
  }

  enviarTicket() {
    if (this.formularioCrearTicket.invalid) {
      const camposFaltantes = this.obtenerCamposInvalidos(this.formularioCrearTicket);

      this.formularioCrearTicket.markAllAsTouched();

      mostrarAlertaToast(`❗Faltan datos obligatorios: ${camposFaltantes.join(', ')}`);
      return;
    }

    const payloadFinal = {
      ...this.formularioCrearTicket.value,
      departamento_id: this.formularioCrearTicket.value.departamento
    };
    delete payloadFinal.departamento;

    const token = localStorage.getItem('token');
    const headers = token ? new HttpHeaders().set('Authorization', `Bearer ${token}`) : new HttpHeaders();

    this.http.post<{ mensaje: string }>(this.apiUrl, payloadFinal, { headers }).subscribe({
      next: () => {
        mostrarAlertaToast('✅ Ticket creado correctamente.');
        this.formularioCrearTicket.reset();
      },
      error: (error) => {
        mostrarAlertaErrorDesdeStatus(error.status);
      }
    });
  }





}
