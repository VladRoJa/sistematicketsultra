// src/app/mantenimiento-edificio/mantenimiento-edificio.component.ts

import { Component, Input, OnInit, OnChanges, SimpleChanges, Output, EventEmitter } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormGroup, FormControl, Validators, ReactiveFormsModule, FormsModule } from '@angular/forms';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatSelectModule } from '@angular/material/select';
import { MatInputModule } from '@angular/material/input';
import { limpiarCamposDependientes } from 'src/app/utils/formularios.helper';

@Component({
  selector: 'app-mantenimiento-edificio',
  standalone: true,
  imports: [
    CommonModule,
    ReactiveFormsModule,
    FormsModule,
    MatFormFieldModule,
    MatSelectModule,
    MatInputModule
  ],
  templateUrl: './mantenimiento-edificio.component.html',
  styleUrls: []
})
export class MantenimientoEdificioComponent implements OnInit, OnChanges {
  @Input() parentForm!: FormGroup;
  @Output() formularioValido = new EventEmitter<any>();

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

  ngOnInit(): void {
    this.registrarControles();

    this.parentForm.valueChanges.subscribe(() => {
      if (this.parentForm.valid) {
        this.emitirPayload();
      }
    });
  }

  ngOnChanges(changes: SimpleChanges): void {
    if (changes['parentForm'] && this.parentForm) {
      this.registrarControles();
    }
  }

  onCategoriaChange(): void {
    limpiarCamposDependientes(this.parentForm, ['subcategoria', 'detalle']);
  }

  onSubcategoriaChange(): void {
    limpiarCamposDependientes(this.parentForm, ['subsubcategoria']);
  }

  registrarControles(): void {
    const campos = ['categoria', 'subcategoria', 'detalle', 'descripcion'];
    for (const campo of campos) {
      if (!this.parentForm.get(campo)) {
        this.parentForm.addControl(campo, new FormControl('', Validators.required));
      }
    }
  }

  emitirPayload(): void {
    this.formularioValido.emit({
      departamento_id: 1,
      categoria: this.parentForm.value.categoria,
      subcategoria: this.parentForm.value.subcategoria,
      subsubcategoria: this.parentForm.value.subsubcategoria,
      descripcion: this.parentForm.value.descripcion
    });
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
