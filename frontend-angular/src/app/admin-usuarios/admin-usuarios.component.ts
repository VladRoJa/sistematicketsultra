// admin-usuarios.component.ts

import { Component, OnInit } from '@angular/core';
import { HttpClient, HttpHeaders } from '@angular/common/http';
import { AuthService } from '../services/auth.service';

@Component({
  selector: 'app-admin-usuarios',
  templateUrl: './admin-usuarios.component.html',
  styleUrls: ['./admin-usuarios.component.css']
})
export class AdminUsuariosComponent implements OnInit {
  usuarios: any[] = [];
  roles = ['usuario', 'jefe', 'administrador', 'supervisor'];

  constructor(private http: HttpClient, private authService: AuthService) {}

  ngOnInit() {
    this.cargarUsuarios();
  }

  cargarUsuarios() {
    const headers = new HttpHeaders().set('Authorization', `Bearer ${this.authService.getToken()}`);
    this.http.get('http://localhost:5000/api/usuarios', { headers }).subscribe((data: any) => {
      this.usuarios = data;
    });
  }

  cambiarRol(usuarioId: number, nuevoRol: string) {
    const headers = new HttpHeaders().set('Authorization', `Bearer ${this.authService.getToken()}`);
    this.http.put('http://localhost:5000/api/usuarios/cambiar-rol', { usuario_id: usuarioId, nuevo_rol: nuevoRol }, { headers })
      .subscribe(() => {
        alert('Rol actualizado con éxito');
        this.cargarUsuarios();
      });
  }
}
