//admin-permisos.componets.ts

import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { AuthService } from '../services/auth.service';
import { DepartamentoService } from '../services/departamento.service';
import { UsuarioService } from '../services/usuario.service';
import { PermisoService } from '../services/permiso.service'; // Nuevo servicio
import { Router } from '@angular/router';


@Component({
  selector: 'app-admin-permisos',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './admin-permisos.component.html',
  styleUrls: ['./admin-permisos.component.css']
})
export class AdminPermisosComponent implements OnInit {
  usuarios: any[] = [];
  departamentos: any[] = [];
  usuarioSeleccionado!: number; // Usuario seleccionado en el dropdown
  permisosUsuario: any[] = []; // Guardaremos los permisos obtenidos
  permisosSeleccionados: number[] = []; // Guardaremos los permisos seleccionados


  constructor(
    private authService: AuthService,
    private departamentoService: DepartamentoService,
    private usuarioService: UsuarioService,
    private permisoService: PermisoService,
    private router: Router
  ) {}

  ngOnInit() {
    this.cargarUsuarios();
    this.cargarDepartamentos();
  }

  cargarUsuarios() {
    this.usuarioService.getUsuarios().subscribe({
      next: (resp) => {
        // Suponiendo que la respuesta tiene el formato { usuarios: [...] }
        this.usuarios = resp.usuarios;
        console.log("Usuarios cargados:", this.usuarios);
      },
      error: (err) => {
        console.error('Error al cargar usuarios:', err);
      }
    });
  }

  cargarDepartamentos() {
    this.departamentoService.obtenerDepartamentos().subscribe({
      next: (resp) => {
        // Suponiendo que la respuesta tiene el formato { departamentos: [...] }
        this.departamentos = resp.departamentos;
        console.log("Departamentos cargados:", this.departamentos);
      },
      error: (err) => {
        console.error('Error al cargar departamentos:', err);
      }
    });
  }

  cargarPermisos() {
    console.log("Cargando permisos para usuario", this.usuarioSeleccionado);
    this.permisoService.getPermisosUsuario(this.usuarioSeleccionado).subscribe({
      next: (resp) => {
        // Suponiendo que la respuesta tiene el formato { permisos: [...] }
        this.permisosUsuario = resp.permisos;
        console.log("Permisos cargados:", this.permisosUsuario);
      },
      error: (err) => {
        console.error("Error al cargar permisos:", err);
      }
    });
  }

  // Valida si el usuario tiene permiso para el departamento dado
  tienePermiso(departamentoId: number): boolean {
    return this.permisosUsuario.some((permiso) => permiso.departamento_id === departamentoId);
  }

  togglePermiso(departamentoId: number, event: Event) {
    const isChecked = (event.target as HTMLInputElement).checked;
  
    if (isChecked) {
      this.permisosSeleccionados.push(departamentoId);
    } else {
      const index = this.permisosSeleccionados.indexOf(departamentoId);
      if (index !== -1) {
        this.permisosSeleccionados.splice(index, 1);
      }
    }
    console.log("Permisos seleccionados:", this.permisosSeleccionados);
  }
  
  guardarPermisos() {
    console.log("Guardando permisos:", this.permisosSeleccionados);
    // Envías permisosSeleccionados al backend para que los asigne/revoque
  }


}
