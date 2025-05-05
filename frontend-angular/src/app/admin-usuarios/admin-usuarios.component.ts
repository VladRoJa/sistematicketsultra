// admin-usuarios.component.ts

import { Component, OnInit } from '@angular/core';
import { HttpClient, HttpHeaders } from '@angular/common/http';
import { AuthService } from '../services/auth.service';
import { environment } from 'src/environments/environment';

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
    this.http.get(`${environment.apiUrl}/usuarios`, { headers }).subscribe((data: any) => {
      this.usuarios = data;
    });
  }

  cambiarRol(usuarioId: number, nuevoRol: string) {
    const headers = new HttpHeaders().set('Authorization', `Bearer ${this.authService.getToken()}`);
    this.http.put(`${environment.apiUrl}/usuarios/cambiar-rol`, { usuario_id: usuarioId, nuevo_rol: nuevoRol }, { headers })
      .subscribe(() => {
        alert('Rol actualizado con éxito');
        this.cargarUsuarios();
      });
  }
}
