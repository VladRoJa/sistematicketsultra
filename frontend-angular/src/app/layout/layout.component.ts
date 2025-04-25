// src/app/layout/layout.component.ts

import { Component, ElementRef, ViewChild, Renderer2, OnInit, AfterViewInit } from '@angular/core';
import { Router, RouterModule, RouterOutlet } from '@angular/router';
import { HttpClient, HttpHeaders } from '@angular/common/http';
import { MatDialog, MatDialogModule } from '@angular/material/dialog';
import { MatToolbarModule } from '@angular/material/toolbar';
import { MatIconModule } from '@angular/material/icon';
import { MatButtonModule } from '@angular/material/button';
import { CommonModule } from '@angular/common';
import { EliminarTicketDialogComponent } from '../eliminar-ticket-dialog/eliminar-ticket-dialog.component';

@Component({
  selector: 'app-layout',
  standalone: true,
  templateUrl: './layout.component.html',
  styleUrls: ['./layout.component.css'],
  imports: [
    CommonModule,
    RouterModule,
    RouterOutlet,
    MatToolbarModule,
    MatIconModule,
    MatButtonModule,
    MatDialogModule
  ]
})
export class LayoutComponent implements OnInit, AfterViewInit {
  @ViewChild('indicator', { static: true }) indicator!: ElementRef;
  esAdmin = false;
  currentSubmenu: string = 'Tickets';
  submenuVisible: boolean = false;
  estiloIndicador: any = {};
  submenuActivo: { [key: string]: string } = {};

  menuItems = [
    {
      label: 'Tickets',
      path: '/main/ver-tickets',
      submenu: [
        { label: 'Ver Tickets', path: '/main/ver-tickets' },
        { label: 'Crear Ticket', path: '/main/crear-ticket' }
      ]
    },
    {
      label: 'Inventario',
      path: '/inventario/productos',
      submenu: [
        { label: 'Productos', path: '/inventario/productos' },
        { label: 'Movimientos', path: '/inventario/movimientos' },
        { label: 'Existencias', path: '/inventario/existencias' },
        { label: 'Reportes', path: '/inventario/reportes' },
        { label: 'Carga Masiva', path: '/carga-masiva' }
      ]
    },
    {
      label: 'Permisos',
      path: '/admin-permisos',
      submenu: []
    },
    {
      label: 'Ajustes',
      path: '/ajustes',
      submenu: []
    }
  ];

  private apiUrl = 'http://localhost:5000/api/tickets';

  constructor(
    private router: Router,
    private http: HttpClient,
    private dialog: MatDialog,
    private renderer: Renderer2
  ) {}

  timeoutSubmenu: any;
  ocultarTimeout: any;
  estiloIndicadorSubmenu: any = {};

  ngOnInit(): void {
    const userString = localStorage.getItem('user');
    if (userString) {
      const user = JSON.parse(userString);
      this.esAdmin = user.rol === 'ADMINISTRADOR';
    }
  }

  ngAfterViewInit(): void {
    const firstItem = document.querySelector('.nav-item') as HTMLElement;
    if (firstItem) {
      setTimeout(() => this.moverIndicador({ target: firstItem } as any), 0);
    }
  }

  cerrarSesion(): void {
    localStorage.removeItem('token');
    localStorage.removeItem('user');
    this.router.navigate(['/login']);
  }

  openEliminarDialog(): void {
    const dialogRef = this.dialog.open(EliminarTicketDialogComponent, {
      width: '400px',
      data: {}
    });

    dialogRef.afterClosed().subscribe((ticketId: number | null) => {
      if (ticketId) {
        this.eliminarTicket(ticketId);
      }
    });
  }

  eliminarTicket(ticketId: number): void {
    if (!ticketId) {
      alert('No se especificó un ID de ticket.');
      return;
    }

    const token = localStorage.getItem('token');
    if (!token) {
      console.error('No hay token, no se puede eliminar el ticket.');
      return;
    }

    const headers = new HttpHeaders()
      .set('Authorization', `Bearer ${token}`)
      .set('Content-Type', 'application/json');

    this.http.delete(`${this.apiUrl}/delete/${ticketId}`, { headers }).subscribe({
      next: (response: any) => alert(response.mensaje),
      error: () => alert('No se pudo eliminar el ticket.')
    });
  }

  moverIndicador(event: MouseEvent): void {
    const target = event.target as HTMLElement;
    if (target.classList.contains('nav-item')) {
      const rect = target.getBoundingClientRect();
      const containerRect = target.parentElement!.getBoundingClientRect();

      this.estiloIndicador = {
        left: `${rect.left - containerRect.left}px`,
        width: `${rect.width}px`
      };
    }
  }

  cambiarMenu(menu: string): void {
    this.currentSubmenu = menu;
    this.submenuVisible = true;
    this.estiloIndicadorSubmenu = {};
  }


  navegarConCambio(path: string, submenu: string): void {
    this.currentSubmenu = submenu;
    this.router.navigateByUrl(path);
  }
  get submenuActual() {
    return this.menuItems.find(m => m.label === this.currentSubmenu)?.submenu || [];
  }

  ocultarSubmenu(): void {
    this.timeoutSubmenu = setTimeout(() => {
      this.submenuVisible = false;
    }, 150); // pequeño retraso para permitir pasar al submenú
  }


  programarOcultarSubmenu(): void {
    this.ocultarTimeout = setTimeout(() => {
      this.submenuVisible = false;
    }, 300); // Delay para permitir pasar de menú a submenú
  }
  
  cancelarOcultarSubmenu(): void {
    if (this.ocultarTimeout) {
      clearTimeout(this.ocultarTimeout);
    }
  }
  moverIndicadorSubmenu(event: MouseEvent): void {
    const target = event.target as HTMLElement;
    const rect = target.getBoundingClientRect();
    const containerRect = target.parentElement!.getBoundingClientRect();
  
    this.estiloIndicadorSubmenu = {
      left: `${rect.left - containerRect.left}px`,
      width: `${rect.width}px`
    };
  }
  
  limpiarIndicadorSubmenu(): void {
    this.estiloIndicadorSubmenu = {};
  }

  seleccionarSubmenu(label: string, path: string): void {
    this.submenuActivo[this.currentSubmenu] = label;
    this.router.navigateByUrl(path);
  }
}
