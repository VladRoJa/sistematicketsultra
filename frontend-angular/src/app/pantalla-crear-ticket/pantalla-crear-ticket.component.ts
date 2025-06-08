// pantalla-crear-ticket.component.ts (actualizado)

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
    SistemasComponent
  ],
  templateUrl: './pantalla-crear-ticket.component.html',
  styleUrls: ['./pantalla-crear-ticket.component.css']
})
export class PantallaCrearTicketComponent implements OnInit {

  formularioMantenimiento!: FormGroup;
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
    this.formularioMantenimiento = this.fb.group({
      departamento: [null, Validators.required],
      tipoMantenimiento: [null]
    });

    this.formularioMantenimiento.get('tipoMantenimiento')?.valueChanges.subscribe(() => {
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
      if (this.formularioMantenimiento.contains(campo)) {
        this.formularioMantenimiento.removeControl(campo);
      }
    });
  }

  // 🔥 Aquí viene la clave: escuchamos el payload de los subformularios
  recibirPayloadDesdeFormulario(payload: any) {
    const token = localStorage.getItem('token');
    const headers = token ? new HttpHeaders().set('Authorization', `Bearer ${token}`) : new HttpHeaders();

    console.log("📡 Enviando al backend:", payload);

    this.http.post<{ mensaje: string }>(this.apiUrl, payload, { headers }).subscribe({
      next: () => {
        mostrarAlertaToast('✅ Ticket creado correctamente.');
        this.formularioMantenimiento.reset();
      },
      error: (error) => {
        mostrarAlertaErrorDesdeStatus(error.status);
      }
    });
  }
}
