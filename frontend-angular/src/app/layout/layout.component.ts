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
import { environment } from 'src/environments/environment';

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
  submenuVisible = false;
  estiloIndicador: any = {};
  estiloIndicadorSubmenu: any = {};
  submenuActivo: { [key: string]: string } = {};
  timeoutSubmenu: any;
  ocultarTimeout: any;

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

  private apiUrl = `${environment.apiUrl}/tickets`;

  constructor(
    private router: Router,
    private http: HttpClient,
    private dialog: MatDialog,
    private renderer: Renderer2
  ) {}

  ngOnInit(): void {
    this.verificarRolUsuario();
  }

  ngAfterViewInit(): void {
    this.inicializarIndicador();
  }

  private verificarRolUsuario(): void {
    const userString = localStorage.getItem('user');
    if (userString) {
      const user = JSON.parse(userString);
      this.esAdmin = user.rol === 'ADMINISTRADOR';
    }
  }

  private inicializarIndicador(): void {
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

  private eliminarTicket(ticketId: number): void {
    if (!ticketId) {
      alert('No se especificó un ID de ticket.');
      return;
    }

    const token = localStorage.getItem('token');
    if (!token) {
      console.error('No hay token disponible.');
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

  cambiarMenu(menu: string): void {
    this.currentSubmenu = menu;
    this.submenuVisible = true;
    this.estiloIndicadorSubmenu = {};
  }

  seleccionarSubmenu(label: string, path: string): void {
    this.submenuActivo[this.currentSubmenu] = label;
    this.router.navigateByUrl(path);
  }

  navegarConCambio(path: string, submenu: string): void {
    this.currentSubmenu = submenu;
    this.router.navigateByUrl(path);
  }

  ocultarSubmenu(): void {
    this.timeoutSubmenu = setTimeout(() => {
      this.submenuVisible = false;
    }, 150);
  }

  programarOcultarSubmenu(): void {
    this.ocultarTimeout = setTimeout(() => {
      this.submenuVisible = false;
    }, 300);
  }

  cancelarOcultarSubmenu(): void {
    if (this.ocultarTimeout) {
      clearTimeout(this.ocultarTimeout);
    }
  }

  get submenuActual() {
    return this.menuItems.find(m => m.label === this.currentSubmenu)?.submenu || [];
  }
}
