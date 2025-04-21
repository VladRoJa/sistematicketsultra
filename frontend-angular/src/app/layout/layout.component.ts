// src/app/layout/layout.component.ts
import { Component, OnInit } from '@angular/core';
import { Router } from '@angular/router';
import { CommonModule } from '@angular/common';
import { RouterOutlet, RouterLink } from '@angular/router';
import { MatToolbarModule } from '@angular/material/toolbar';
import { MatMenuModule } from '@angular/material/menu';
import { MatButtonModule } from '@angular/material/button';
import { MatDividerModule } from '@angular/material/divider';
import { FormsModule } from '@angular/forms';
import { HttpClient, HttpHeaders } from '@angular/common/http';
import { MatDialog, MatDialogModule } from '@angular/material/dialog';
import { EliminarTicketDialogComponent } from '../eliminar-ticket-dialog/eliminar-ticket-dialog.component';
import { MatIconModule } from '@angular/material/icon';


@Component({
  selector: 'app-layout',
  standalone: true,
  imports: [
    CommonModule,
    RouterOutlet,
    RouterLink,
    MatToolbarModule,
    MatMenuModule,
    MatButtonModule,
    MatDividerModule,
    FormsModule,
    MatDialogModule,
    MatIconModule
  ],
  templateUrl: './layout.component.html', // ✅ Usa templateUrl
  styleUrls: ['./layout.component.css']   // ✅ Usa styleUrls
})

export class LayoutComponent implements OnInit {
  esAdmin: boolean = false;
  private apiUrl = 'http://localhost:5000/api/tickets';

  constructor(
    private router: Router,
    private http: HttpClient,
    private dialog: MatDialog // Inyectamos el servicio MatDialog
  ) {
    console.log('LayoutComponent constructor');
  }

  ngOnInit(): void {
    const userString = localStorage.getItem('user');
    if (userString) {
      const user = JSON.parse(userString);
      this.esAdmin = user.rol === 'ADMINISTRADOR';
      console.log('Es admin:', this.esAdmin);
    }
  }

  cerrarSesion(): void {
    const confirmar = window.confirm("¿Estás seguro que deseas cerrar sesión?");
    if (confirmar) {
      localStorage.removeItem('token');
      localStorage.removeItem('user');
      this.router.navigate(['/login']);
    }
  }

  irAGestionPermisos(): void {
    this.router.navigate(['/admin-permisos']);
  }

  // Abrimos el diálogo de eliminación
  openEliminarDialog(): void {
    const dialogRef = this.dialog.open(EliminarTicketDialogComponent, {
      width: '400px',
      data: {}  // No se pasa un ticketId, se pedirá en el diálogo
    });
  
    dialogRef.afterClosed().subscribe((ticketId: number | null) => {
      if (ticketId) {
        this.eliminarTicket(ticketId);
      } else {
        console.log("Eliminación cancelada.");
      }
    });
  }
  
  // Función para eliminar el ticket
  eliminarTicket(ticketId: number): void {
    // Si prefieres una validación extra (por si el modal no pasa un ID válido):
    if (!ticketId) {
      alert("No se especificó un ID de ticket.");
      return;
    }
  
    const token = localStorage.getItem('token');
    if (!token) {
      console.error("No hay token, no se puede eliminar el ticket.");
      return;
    }
  
    // Ya no llamamos a confirm(), porque el modal se encarga de esa confirmación
    const headers = new HttpHeaders()
      .set('Authorization', `Bearer ${token}`)
      .set('Content-Type', 'application/json');
  
    this.http.delete(`${this.apiUrl}/delete/${ticketId}`, { headers }).subscribe({
      next: (response: any) => {
        console.log(`Ticket ${ticketId} eliminado.`);
        alert(response.mensaje);
      },
      error: (error) => {
        console.error(`Error al eliminar el ticket:`, error);
        alert("No se pudo eliminar el ticket.");
      }
    });
  }
  
}
