// pantalla-crear-ticket.component.ts

import { Component, OnInit } from '@angular/core';
import { HttpClient, HttpHeaders } from '@angular/common/http';
import { CommonModule } from '@angular/common';
import { Router } from '@angular/router';
import Swal from 'sweetalert2';
import { FormBuilder, FormGroup, Validators, ReactiveFormsModule, FormsModule } from '@angular/forms';

// Componentes específicos por tipo de mantenimiento
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

  // Formulario reactivo principal
  formularioMantenimiento!: FormGroup;
  mensaje: string = '';

  // Lista de departamentos disponibles
  departamentos = [
    { id: 1, nombre: 'Mantenimiento' },
    { id: 2, nombre: 'Finanzas' },
    { id: 3, nombre: 'Marketing' },
    { id: 4, nombre: 'Gerencia Deportiva' },
    { id: 5, nombre: 'Recursos Humanos' },
    { id: 6, nombre: 'Compras' },
    { id: 7, nombre: 'Sistemas' }
  ];

  // Categorías precargadas por departamento
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

  // Seguimiento de categorías manuales frecuentes
  categoriaHistorial: { [key: string]: number } = {};

  private apiUrl = 'http://localhost:5000/api/tickets/create';

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
      descripcion: ['', Validators.required]
    });
  }

  // Al cambiar de departamento, reinicia las categorías relacionadas
  cargarFormulario() {
    const depto = this.formularioMantenimiento.get('departamento')?.value;
    if (depto) {
      this.formularioMantenimiento.get('categoria')?.reset();
      this.formularioMantenimiento.get('nuevaCategoria')?.reset();
    }
  }

  // Si el usuario escribe una nueva categoría, la registra y si es frecuente, la guarda
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

  // Obtiene el nombre legible del departamento
  getNombreDepartamentoSeleccionado(): string | null {
    const id = this.formularioMantenimiento.get('departamento')?.value;
    const depto = this.departamentos.find(dep => dep.id === id);
    return depto ? depto.nombre : null;
  }

  // Envía el formulario al backend
  onSubmit() {
    const datos = this.formularioMantenimiento.value;
  
    // Forzar valores cuando el tipo de mantenimiento es "aparatos"
    if (datos.tipoMantenimiento === 'aparatos') {
      datos.categoria = 'Aparatos';
      datos.descripcion = datos.problema_detectado;
  
      this.formularioMantenimiento.patchValue({
        categoria: datos.categoria,
        descripcion: datos.descripcion
      });
    }
  
    // Validación condicional según el tipo de mantenimiento
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
        Swal.fire({
          toast: true,
          position: 'bottom-end',
          icon: 'success',
          title: '✅ Ticket creado correctamente.',
          showConfirmButton: false,
          timer: 2500
        });
  
        this.formularioMantenimiento.reset();
      },
      error: (error) => {
        Swal.fire({
          toast: true,
          position: 'top-end',
          icon: 'error',
          title: error.status === 400 ? "⚠️ Faltan datos obligatorios."
                : error.status === 401 ? "🔒 No autorizado, inicia sesión."
                : "❌ Error interno en el servidor.",
          showConfirmButton: false,
          timer: 2500
        });
      }
    });
  }
  
  
}
