// src/app/mantenimiento-edificio/mantenimiento-edificio.component.ts

import { Component, Input, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormGroup, FormControl, Validators, ReactiveFormsModule, FormsModule } from '@angular/forms';

@Component({
  selector: 'app-mantenimiento-edificio',
  standalone: true,
  imports: [CommonModule, ReactiveFormsModule, FormsModule],
  templateUrl: './mantenimiento-edificio.component.html',
  styleUrls: []
})
export class MantenimientoEdificioComponent implements OnInit {
  @Input() parentForm!: FormGroup;

  // Categoría → Subcategoría → Sub-subcategorías
  jerarquiaMantenimiento: { [categoria: string]: { [sub: string]: string[] } } = {
    "Inmueble": {
      "extintores": ["Recarga", "Mal colocación", "Sin etiqueta"],
      "paredes": ["Humedad", "Grietas", "Manchas", "Daños estructurales"],
      "techos": ["Filtraciones", "Desprendimientos", "Fugas"],
      "pintura": ["Descascarado", "Requiere retoque", "Dañado por humedad"],
      "Albañileria": ["Reparación menor", "Reparación estructural", "Desniveles"],
      "limpieza exterior": ["Suciedad visible", "Restos de construcción", "Graffitis"],
      "Pisos": ["Desnivelado", "Roto", "Resbaloso", "Despegado"]
    },
    "AC y ventilación": {
      "ventiladores": ["No enciende", "Hace ruido", "Vibración"],
      "Extractores": ["No funciona", "Filtro sucio", "Hace ruido"],
      "equipos": ["Sin enfriar", "Ruidos extraños", "Fugas"],
      "minisplits": ["No enciende", "Gotea agua", "Filtro sucio"]
    },
    "Sanitarios": {
      "Muebles Sanitarios": ["Fuga de agua", "Obstrucción", "Daño estructural"],
      "llaves": ["No cierra bien", "Goteo", "Oxidación"],
      "Accesorios": ["Roto", "Faltante", "Mal instalado"],
      "Servicios": ["Sin agua", "Baja presión", "Mal olor"],
      "Equipo Hidro": ["Falla de bomba", "Ruido", "No prende"],
      "Boilers": ["No calienta", "Fuga", "Apagado"],
      "Sistema Hidro": ["Baja presión", "No funciona", "Fugas"]
    },
    "Instalación Eléctrica": {
      "TR": ["Sin energía", "Daños visibles", "Falla general"],
      "Contactos": ["No funciona", "Chispazos", "Suelto"],
      "Centro de carga": ["Interruptores dañados", "Sobrecalentamiento"],
      "Servicios": ["Cortes frecuentes", "Voltaje inestable"],
      "Gestion": ["Monitoreo fallido", "Alarmas no responden"],
      "Servicio Automotriz": ["Conexión de carga", "Luz de revisión encendida"]
    },
    "Gasolina": {
      "": ["Fuga de combustible", "Olor fuerte", "Desperfecto en tanque"]
    },
    "Iluminación": {
      "Letreros": ["Luz fundida", "Intermitente", "No prende"],
      "Iluminación interna": ["Parpadea", "Fundida", "Cable suelto"],
      "Iluminación externa": ["Apagada de noche", "Luz débil", "Daño en carcasa"]
    }
  };
  

  categoriaSeleccionada: string | null = null;
  subcategoriaSeleccionada: string | null = null;
  subsubcategoriaSeleccionada: string | null = null;
  descripcionAdicional: string = '';

  ngOnInit(): void {
  }
  

  getCategorias(): string[] {
    return Object.keys(this.jerarquiaMantenimiento);
  }

  getSubcategorias(categoria: string): string[] {
    return this.jerarquiaMantenimiento[categoria]
      ? Object.keys(this.jerarquiaMantenimiento[categoria])
      : [];
  }

  getSubsubcategorias(categoria: string, subcategoria: string): string[] {
    return this.jerarquiaMantenimiento[categoria]?.[subcategoria] || [];
  }
}
