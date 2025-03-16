//pantalla-crear-ticket.ts

import { Component, OnInit } from '@angular/core';
import { HttpClient, HttpHeaders } from '@angular/common/http';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { Router } from '@angular/router';
import Swal from 'sweetalert2';

@Component({
  selector: 'app-pantalla-crear-ticket',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './pantalla-crear-ticket.component.html',
  styleUrls: ['./pantalla-crear-ticket.component.css']
})
export class PantallaCrearTicketComponent implements OnInit {
  descripcion: string = '';
  departamento: number | null = null;
  criticidad: number | null = null;
  categoriaSeleccionada: string = ''; // Categoría seleccionada por el usuario
  nuevaCategoria: string = ''; // Nueva categoría ingresada por el usuario
  mensaje: string = '';

  // Historial de categorías ingresadas manualmente
  categoriaHistorial: { [key: string]: number } = {};

  // 🔥 Asegurarse de definir correctamente los departamentos
  departamentos = [
    { id: 1, nombre: 'Mantenimiento' },
    { id: 2, nombre: 'Finanzas' },
    { id: 3, nombre: 'Marketing' },
    { id: 4, nombre: 'Gerencia Deportiva' },
    { id: 5, nombre: 'Recursos Humanos' },
    { id: 6, nombre: 'Compras' },
    { id: 7, nombre: 'Sistemas' }
  ];

  // Lista de categorías dinámicas por departamento
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

    6: ["Bebidas para la venta"], // ⚠️ Aún pendiente de definir para Compras

    7: ["Equipo de gerencia"] // ⚠️ Aún pendiente de definir para Sistemas
  };

  private apiUrl = 'http://localhost:5000/api/tickets/create';

  constructor(private http: HttpClient, private router: Router) {}

  ngOnInit() {}

  cargarFormulario() {
    console.log("📌 Departamento seleccionado:", this.departamento);
  
    // Reiniciar la categoría seleccionada
    this.categoriaSeleccionada = '';
    this.nuevaCategoria = '';
  
    // Verificar si hay categorías disponibles para el departamento
    if (this.departamento && this.categoriasPorDepartamento[this.departamento].length === 0) {
      console.warn("⚠️ No hay categorías definidas para este departamento.");
    }
  }
  
  agregarCategoriaManual() {
    if (this.nuevaCategoria.trim() !== '') {
      if (!this.categoriasPorDepartamento[this.departamento!].includes(this.nuevaCategoria)) {
        if (this.categoriaHistorial[this.nuevaCategoria]) {
          this.categoriaHistorial[this.nuevaCategoria]++;
        } else {
          this.categoriaHistorial[this.nuevaCategoria] = 1;
        }

        // Si una categoría manualmente ingresada se ha repetido 3 veces, se agrega a la lista
        if (this.categoriaHistorial[this.nuevaCategoria] >= 3) {
          this.categoriasPorDepartamento[this.departamento!].push(this.nuevaCategoria);
        }
      }

      this.categoriaSeleccionada = this.nuevaCategoria;
      this.nuevaCategoria = '';
    }
  }

  onSubmit() {
    // ❌ Verifica si faltan campos
    if (!this.descripcion || !this.departamento || !this.criticidad || !this.categoriaSeleccionada) {
        this.mensaje = "⚠️ Por favor, llena todos los campos.";
        return;
    }

    // ✅ Borra el mensaje de error cuando todos los campos están llenos
    this.mensaje = "";

    const token = localStorage.getItem('token');
    const headers = token
      ? new HttpHeaders().set('Authorization', `Bearer ${token}`)
      : new HttpHeaders();

    let datosFormulario = {
      descripcion: this.descripcion.trim(),
      departamento_id: this.departamento,
      criticidad: Number(this.criticidad),
      categoria: this.categoriaSeleccionada
    };

    console.log("📡 Enviando datos:", datosFormulario);

    this.http.post<{ mensaje: string }>(this.apiUrl, datosFormulario, { headers }).subscribe({
      next: () => {
        // ✅ Muestra mensaje de éxito
        Swal.fire({
          toast: true,
          position: 'bottom-end',
          icon: 'success',
          title: '✅ Ticket creado correctamente.',
          showConfirmButton: false,
          timer: 2500
        });

        // ✅ Restablece el formulario
        setTimeout(() => {
          this.descripcion = "";
          this.departamento = null;
          this.criticidad = null;
          this.categoriaSeleccionada = "";
          this.nuevaCategoria = "";
        }, 1000);
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