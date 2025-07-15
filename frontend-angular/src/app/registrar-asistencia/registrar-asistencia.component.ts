import { Component, OnInit } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { AsistenciaResponse } from '../models/asistencia-response.model';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatButtonModule } from '@angular/material/button';
import { MatSelectModule } from '@angular/material/select';
import { MatDialog } from '@angular/material/dialog';
import { DialogoConfirmacionComponent } from '../shared/dialogo-confirmacion/dialogo-confirmacion.component';

@Component({
  selector: 'app-registrar-asistencia',
  standalone: true,
  imports: [
    CommonModule,
    FormsModule,
    MatFormFieldModule,
    MatInputModule,
    MatButtonModule,
    MatSelectModule
  ],
  templateUrl: './registrar-asistencia.component.html',
  styleUrls: ['./registrar-asistencia.component.scss']
})
export class RegistrarAsistenciaComponent implements OnInit {
  numeroEmpleado: number | null = null;
  sucursalId: number | null = null;
  loading = false;
  respuesta?: AsistenciaResponse;
  sucursales: { sucursal_id: number, sucursal: string }[] = [];
  usuarioSesion: any = {};

  constructor(private http: HttpClient, private dialog: MatDialog) {}

  ngOnInit() {
    this.http.get<any>('/api/auth/session-info').subscribe({
      next: data => {
        console.log('Usuario de sesión:', data);
        this.usuarioSesion = data.user;
        this.numeroEmpleado = data.user.id;
        this.sucursalId = data.user.sucursal_id; 
      }
    });

    this.http.get<any[]>('/api/sucursales/listar').subscribe({
      next: sucs => {
        this.sucursales = sucs;
      }
    });
  }


  registrarAsistencia() {
    if (!this.numeroEmpleado || !this.sucursalId) return;

    // Si cambió la sucursal, mostrar modal de confirmación
    if (this.sucursalId !== this.usuarioSesion.sucursal_id) {
      this.dialog.open(DialogoConfirmacionComponent, {
        data: {
          titulo: 'Confirmar cambio de sucursal',
          mensaje: 'Estás marcando asistencia en una sucursal distinta a la de tu sesión. ¿Deseas continuar?',
          textoAceptar: 'Sí, confirmar',
          textoCancelar: 'Cancelar'
        }
      }).afterClosed().subscribe(confirmado => {
        if (confirmado) {
          this.enviarAsistencia();
        }
      });
    } else {
      this.enviarAsistencia();
    }
  }

  private enviarAsistencia() {
    this.loading = true;
    this.respuesta = undefined;
    this.http.post<AsistenciaResponse>('/api/asistencia/registrar', {
      usuario_id: this.numeroEmpleado,
      sucursal_id: this.sucursalId
    }).subscribe({
      next: resp => {
        this.respuesta = resp;
        this.loading = false;
      },
      error: err => {
        this.respuesta = {
          ok: false,
          mensaje: err.error?.mensaje || 'Error desconocido'
        };
        this.loading = false;
      }
    });
  }
}
