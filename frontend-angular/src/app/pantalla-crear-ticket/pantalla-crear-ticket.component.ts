// pantalla-crear-ticket.component.ts (actualizado)

import { Component, OnInit } from '@angular/core';
import { HttpClient, HttpHeaders } from '@angular/common/http';
import { CommonModule } from '@angular/common';
import { Router } from '@angular/router';
import { FormBuilder, FormGroup, Validators, ReactiveFormsModule, FormsModule } from '@angular/forms';
import { mostrarAlertaToast, mostrarAlertaErrorDesdeStatus  } from '../utils/alertas';
import { environment } from 'src/environments/environment';
import { MantenimientoAparatosComponent } from '../mantenimiento-aparatos/mantenimiento-aparatos.component';
import { MantenimientoEdificioComponent } from '../mantenimiento-edificio/mantenimiento-edificio.component';

@Component({
  selector: 'app-pantalla-crear-ticket',
  standalone: true,
  imports: [
    CommonModule,
    FormsModule,
    ReactiveFormsModule,
    MantenimientoEdificioComponent,
    MantenimientoAparatosComponent
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

  categoriasPorDepartamento: { [key: number]: string[] } = {
    1: ["Cardio", "Selectorizado", "Peso libre", "Tapicería", "Aire acondicionado", "Bodega", "Cancelería", "Extintores",
        "Fachada", "Hidroneumático", "Iluminación", "Inmueble", "Instalación eléctrica", "Lockers", "Piso de hule negro",
        "Recepción", "Salón de clases", "Sanitarios", "Ultrakids", "Ventilación / extracción", "Letrero luminoso"],
    2: ["Facturación", "Devolución por cobro erróneo en sistema", "Devolución por cobro erróneo en terminal",
        "Aclaración de pago no reflejado", "Permisos y licencia"],
    3: ["Material promocional", "Vinilos y publicidad interna", "Landing page", "Etiquetas y logos deportivos"],
    4: ["Accesorios para equipos", "Accesorios para clases", "Analizador de composición corporal", "App Ultra",
        "Instructores de clases", "Instructores de piso", "Instructores personalizados"],
    5: ["Incidencia en nómina", "Vacantes", "Uniformes", "Tarjeta de nómina", "Entrega de finiquitos", "Bajas de personal"],
    6: ["Bebidas para la venta"],
    7: ["Computadora Recepción", "Computadora Gerente", "Torniquete 1 (Junto a Recepcion)", "Torniquete 2 (Retirado de recepcion)",
        "Sonido Ambiental (Bocinas, Amplificador)", "Sonido en Salones", "Tablet 1 (Computadora recepcion)",
        "Tablet 2 (Computadora Gerente)", "Impresora multifuncional", "Impresora termica (Recepcion)",
        "Impresora termica (Gerente)", "Terminal (Recepcion)", "Terminal (Gerente)", "Alarma", "Telefono", "Internet", "Camaras"]
  };

  categoriaHistorial: { [key: string]: number } = {};
  private apiUrl = `${environment.apiUrl}/tickets/create`;

  constructor(
    private http: HttpClient,
    private router: Router,
    private fb: FormBuilder
  ) {}

  ngOnInit() {
    this.formularioMantenimiento = this.fb.group({
      departamento: [null, Validators.required],
      tipoMantenimiento: [null],
      categoria: ['', Validators.required],
      subcategoria: [''],
      subsubcategoria: [''],
      nuevaCategoria: [''],
      criticidad: [null, Validators.required],
      descripcion: ['', Validators.required],
    });

    // Aquí va la lógica que agrega los controles hijos dependiendo el tipo
    this.formularioMantenimiento.get('tipoMantenimiento')?.valueChanges.subscribe(tipo => {
      this.resetCamposTipo();
    });
  }

  // 🔧 Esta es la parte clave: limpiar campos cuando cambia tipo mantenimiento
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

  cargarFormulario() {
    const depto = this.formularioMantenimiento.get('departamento')?.value;
    if (depto) {
      this.formularioMantenimiento.get('categoria')?.reset();
      this.formularioMantenimiento.get('nuevaCategoria')?.reset();
    }
  }

  agregarCategoriaManual() {
    const depto = this.formularioMantenimiento.get('departamento')?.value;
    const nuevaCat = this.formularioMantenimiento.get('nuevaCategoria')?.value;
    if (!depto || !nuevaCat) return;

    if (!this.categoriasPorDepartamento[depto].includes(nuevaCat)) {
      this.categoriaHistorial[nuevaCat] = (this.categoriaHistorial[nuevaCat] || 0) + 1;
      if (this.categoriaHistorial[nuevaCat] >= 3) {
        this.categoriasPorDepartamento[depto].push(nuevaCat);
      }
    }

    this.formularioMantenimiento.patchValue({ categoria: nuevaCat });
    this.formularioMantenimiento.get('nuevaCategoria')?.reset();
  }

  getNombreDepartamentoSeleccionado(): string | null {
    const id = this.formularioMantenimiento.get('departamento')?.value;
    const depto = this.departamentos.find(dep => dep.id === id);
    return depto ? depto.nombre : null;
  }

  onSubmit() {
    const datos = this.formularioMantenimiento.value;

    if (datos.tipoMantenimiento === 'aparatos') {
      datos.categoria = 'Aparatos';
      datos.descripcion = datos.problema_detectado;

      this.formularioMantenimiento.patchValue({
        categoria: datos.categoria,
        descripcion: datos.descripcion
      });
    }

    const tipo = datos.tipoMantenimiento;

    if (
      this.formularioMantenimiento.invalid ||
      (tipo === 'aparatos' && (
        !datos.aparato_id ||
        !datos.problema_detectado ||
        (datos.necesita_refaccion === true && !datos.descripcion_refaccion)
      ))
    ) {
      this.mensaje = "⚠️ Por favor, llena todos los campos.";
      console.log("❌ Formulario inválido:", datos);
      return;
    }

    this.mensaje = "";

    const token = localStorage.getItem('token');
    const headers = token ? new HttpHeaders().set('Authorization', `Bearer ${token}`) : new HttpHeaders();

    const payload = {
      descripcion: datos.descripcion,
      departamento_id: datos.departamento,
      criticidad: datos.criticidad,
      categoria: datos.categoria,
      subcategoria: datos.subcategoria || null,
      subsubcategoria: datos.subsubcategoria || null,
      aparato_id: datos.aparato_id || null,
      problema_detectado: datos.problema_detectado || null,
      necesita_refaccion: datos.necesita_refaccion || false,
      descripcion_refaccion: datos.descripcion_refaccion || null
    };

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
