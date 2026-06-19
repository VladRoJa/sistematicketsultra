// src/app/layout/layout.component.ts

import { Component, ElementRef, ViewChild, Renderer2, OnInit, AfterViewInit, OnDestroy } from '@angular/core';
import { Router, RouterModule, RouterOutlet } from '@angular/router';
import { HttpClient, HttpHeaders } from '@angular/common/http';
import { MatDialog, MatDialogModule } from '@angular/material/dialog';
import { MatToolbarModule } from '@angular/material/toolbar';
import { MatIconModule } from '@angular/material/icon';
import { MatButtonModule } from '@angular/material/button';
import { CommonModule } from '@angular/common';
import { EliminarTicketDialogComponent } from '../eliminar-ticket-dialog/eliminar-ticket-dialog.component';
import { environment } from 'src/environments/environment';
import { ReportarErrorComponent } from '../reportar-error/reportar-error.component';
import { mostrarAlertaToast } from '../utils/alertas';
import { AuthService } from '../services/auth.service';
import { ReauthModalComponent } from '../reauth-modal/reauth-modal.component';
import { InactividadService } from '../services/inactividad.service';
import { SessionService } from '../core/auth/session.service';
import { CdkDragEnd, DragDropModule } from '@angular/cdk/drag-drop';
import { TicketService, TicketValidationSummary } from '../services/ticket.service';
import { Subscription } from 'rxjs';
import { RefrescoService } from '../services/refresco.service';

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
    MatDialogModule,
    DragDropModule
  ]
})
export class LayoutComponent implements OnInit, AfterViewInit, OnDestroy {
  @ViewChild('indicator', { static: true }) indicator!: ElementRef;

  esAdmin = false;
  esSoloLectura = false;
  currentSubmenu: string = 'Tickets';
  submenuVisible = false;
  estiloIndicador: any = {};
  estiloIndicadorSubmenu: any = {};
  submenuActivo: { [key: string]: string } = {};
  timeoutSubmenu: any;
  ocultarTimeout: any;
  menuItems: any[] = [];
  puedeVerMantenimiento = false;
  puedeVerMantenimientoCompleto = false;
  puedeVerMantenimientoOperativo = false;
  puedeVerMantenimientoGerencial = false;
  puedeVerWarehouse = false;
  puedeVerPlanning = false;
  puedeVerInternalDocuments = false;
  puedeVerOpenings = false;

  usuarioLabel = '';
  reporteBugFueArrastrado = false;
  validationSummary: TicketValidationSummary | null = null;
  validationAlertFueArrastrada = false;
  validationAlertPosition = { x: 0, y: 0 };

  private validationSummaryIntervalId: ReturnType<typeof setInterval> | null = null;
  private validationSummaryRefreshSubscription?: Subscription;
  private readonly validationSummaryRefreshMs = 60 * 1000;
  private readonly validationAlertSnoozeMs = 3 * 60 * 1000;
  private readonly validationAlertSnoozeKey = 'suite.ticketValidationAlert.snoozeUntil';
  private readonly validationAlertPositionKey = 'suite.ticketValidationAlert.position';

  private apiUrl = `${environment.apiUrl}/tickets`;

  // ⏳ Configuración de inactividad
  private tiempoInactividad = 45 * 60 * 1000; // 45 minutos en ms
  private temporizadorInactividad: any;
  private reauthPorInactividadAbierto = false;

  constructor(
    private router: Router,
    private http: HttpClient,
    private dialog: MatDialog,
    private renderer: Renderer2,
    private authService: AuthService,
    private inactividadService: InactividadService,
    private session: SessionService,
    private ticketService: TicketService,
    private refrescoService: RefrescoService,
  ) {}

ngOnInit(): void {
  this.verificarRolUsuario();
  const u = this.session.getUser();
  this.usuarioLabel = (u?.username || '').toString();
  this.iniciarTimerInactividad();
  this.inactividadService.registrarCallback(() => this.reiniciarTimerInactividad());

  const menuWarehouse = {
    label: 'Warehouse',
    path: '/warehouse',
    submenu: [
      { label: 'Warehouse', path: '/warehouse' },
      {
        label: 'BI Comercial / Promociones',
        path: '/warehouse/comercial/promociones',
      },
    ],
  };

  const menuNubeCorporativa = {
    label: 'Nube Corporativa',
    path: '/nube-corporativa',
    submenu: [
      { label: 'Biblioteca Interna', path: '/nube-corporativa' },
    ],
  };
  const trackSubmenu = [
    { label: 'Track Diario', path: '/warehouse/track' },
  ];

  if (this.puedeVerKpiDesempenoPorRol()) {
    trackSubmenu.push({
      label: 'KPI Desempeño',
      path: '/warehouse/track/kpi-desempeno',
    });
  }

  const menuTrackDiario = {
    label: 'Track',
    path: '/warehouse/track',
    submenu: trackSubmenu,
  };

  const menuPlanning = {
    label: 'Planeación',
    path: '/planeacion/metas',
    submenu: [
      { label: 'Metas Comerciales', path: '/planeacion/metas' },
    ],
  };

  const menuAperturas = {
    label: 'Aperturas',
    path: '/aperturas',
    submenu: [
      { label: 'Centro de control', path: '/aperturas' },
    ],
  };

  const soloTickets = [
    {
      label: 'Tickets',
      path: '/main/ver-tickets',
      submenu: [
        { label: 'Ver Tickets', path: '/main/ver-tickets' },
        { label: 'Crear Ticket', path: '/main/crear-ticket' }
      ]
    }
  ];

const menuMantenimientoCompleto = [
  {
    label: 'Tickets',
    path: '/main/ver-tickets',
    submenu: [
      { label: 'Ver Tickets', path: '/main/ver-tickets' },
      { label: 'Crear Ticket', path: '/main/crear-ticket' }
    ]
  },
  {
    label: 'Mantenimiento',
    path: '/pm/escritorio-preventivo',
    submenu: [
      { label: 'Escritorio Mantenimiento', path: '/pm/escritorio-preventivo' },
      { label: 'Bitácora', path: '/pm/bitacoras-mobile' },
      { label: 'Consulta / Historial', path: '/pm/consulta-historial' },
      { label: 'Configuración / Programación', path: '/pm/configuracion-programacion' },
      { label: 'Calendario', path: '/pm/calendario' },
    ]
  }
];

const menuMantenimientoOperativo = [
  {
    label: 'Tickets',
    path: '/main/ver-tickets',
    submenu: [
      { label: 'Ver Tickets', path: '/main/ver-tickets' },
      { label: 'Crear Ticket', path: '/main/crear-ticket' }
    ]
  },
  {
    label: 'Mantenimiento',
    path: '/pm/bitacoras-mobile',
    submenu: [
      { label: 'Bitácora', path: '/pm/bitacoras-mobile' },
      { label: 'Escritorio Mantenimiento', path: '/pm/escritorio-preventivo' },
      { label: 'Consulta / Historial', path: '/pm/consulta-historial' },
      { label: 'Calendario', path: '/pm/calendario' },
    ]
  }
];

const menuMantenimientoGerencial = [
  {
    label: 'Tickets',
    path: '/main/ver-tickets',
    submenu: [
      { label: 'Ver Tickets', path: '/main/ver-tickets' },
      { label: 'Crear Ticket', path: '/main/crear-ticket' }
    ]
  },
  {
    label: 'Mantenimiento',
    path: '/pm/escritorio-preventivo',
    submenu: [
      { label: 'Escritorio Mantenimiento', path: '/pm/escritorio-preventivo' },
      { label: 'Consulta / Historial', path: '/pm/consulta-historial' },
      { label: 'Calendario', path: '/pm/calendario' },
    ]
  }
];

  const menuCompleto = [
    {
      label: 'Tickets',
      path: '/main/ver-tickets',
      submenu: [
        { label: 'Ver Tickets', path: '/main/ver-tickets' },
        { label: 'Crear Ticket', path: '/main/crear-ticket' }
      ]
    },
    {
      label: 'Mantenimiento',
      path: '/pm/escritorio-preventivo',
      submenu: [
        { label: 'Escritorio Mantenimiento', path: '/pm/escritorio-preventivo' },
        { label: 'Bitácora', path: '/pm/bitacoras-mobile' },
        { label: 'Consulta / Historial', path: '/pm/consulta-historial' },
        { label: 'Configuración / Programación', path: '/pm/configuracion-programacion' },
        { label: 'Calendario', path: '/pm/calendario' },
      ]
    },
    {
      label: 'Inventario',
      path: '/inventario',
      submenu: [
        { label: 'Inventario', path: '/inventario' },
        { label: 'Movimientos', path: '/inventario/movimientos' },
        { label: 'Existencias', path: '/inventario/existencias' },
        { label: 'Reportes', path: '/inventario/reportes' },
        { label: 'Carga Masiva', path: '/carga-masiva' }
      ]
    },
    {
      label: 'Catálogos',
      path: '/catalogos/marcas',
      submenu: [
        { label: 'Marcas', path: '/catalogos/marcas' },
        { label: 'Proveedores', path: '/catalogos/proveedores' },
        { label: 'Clasificaciones', path: '/catalogos/clasificaciones' },
        { label: 'Unidades de Medida', path: '/catalogos/unidades' },
        { label: 'Grupo Muscular', path: '/catalogos/gruposmusculares' },
        { label: 'Tipos de Inventario', path: '/catalogos/tipos' },
        { label: 'Categorias de Inventario', path: '/catalogos/categorias' },
      ]
    },
    {
      label: 'Asistencia',
      path: '/asistencia/registrar',
      submenu: [
        { label: 'Registrar Asistencia', path: '/asistencia/registrar' },
        { label: 'Reportes', path: '/asistencia/reportes' }
      ]
    },
    {
      label: 'Permisos',
      path: '/admin-usuarios-sucursales/1',
      submenu: [
        { label: 'Sucursales por usuario', path: '/admin-usuarios-sucursales' },
      ]
    }
  ];

  if (this.esSoloLectura) {
    this.menuItems = soloTickets;
  } else if (this.esAdmin) {
    this.menuItems = menuCompleto;
  } else if (this.puedeVerMantenimientoCompleto) {
    this.menuItems = menuMantenimientoCompleto;
  } else if (this.puedeVerMantenimientoOperativo) {
    this.menuItems = menuMantenimientoOperativo;
  } else if (this.puedeVerMantenimientoGerencial) {
    this.menuItems = menuMantenimientoGerencial;
  } else {
    this.menuItems = soloTickets;
  }

if (
  this.puedeVerTrackDiarioPorRol() &&
  !this.menuItems.some((item) => item.label === 'Track')
) {
  this.menuItems = [
    ...this.menuItems,
    menuTrackDiario,
  ];
}

if (
  this.puedeVerAperturasPorRol() &&
  !this.menuItems.some((item) => item.label === 'Aperturas')
) {
  this.puedeVerOpenings = true;
  this.menuItems = [
    ...this.menuItems,
    menuAperturas,
  ];
}

this.habilitarWarehouseEnMenuSiAplica(menuWarehouse);
  this.habilitarPlanningEnMenuSiAplica(menuPlanning);
  this.habilitarInternalDocumentsEnMenuSiAplica(menuNubeCorporativa);
  this.sincronizarMenuConRutaActual();
  this.cargarTicketValidationAlertPosition();
  this.cargarTicketValidationSummary();

  this.validationSummaryIntervalId = setInterval(() => {
    this.cargarTicketValidationSummary();
  }, this.validationSummaryRefreshMs);

  this.validationSummaryRefreshSubscription =
    this.refrescoService.refrescarResumenValidacionTickets$.subscribe(() => {
      this.cargarTicketValidationSummary();
    });
  }

private habilitarWarehouseEnMenuSiAplica(menuWarehouse: any): void {
  if (this.menuItems.some((item) => item.label === 'Warehouse')) {
    return;
  }

  this.http
    .get<any>(`${environment.apiUrl}/warehouse/access`)
    .subscribe({
      next: (response) => {
        const puedeVerWarehouse = Boolean(
          response?.allowed ??
          response?.can_view ??
          response?.canView ??
          response?.has_access ??
          response?.hasAccess ??
          response?.access?.can_view ??
          response?.access?.canView ??
          response?.permissions?.can_view ??
          response?.permissions?.canView ??
          response?.operator?.can_view ??
          response?.operator?.canView ??
          response?.warehouse_access?.can_view ??
          response?.warehouse_access?.canView
        );

        if (!puedeVerWarehouse) {
          return;
        }

        if (this.menuItems.some((item) => item.label === 'Warehouse')) {
          return;
        }

        this.puedeVerWarehouse = true;
        this.menuItems = [
          ...this.menuItems,
          menuWarehouse,
        ];

        this.sincronizarMenuConRutaActual();
      },
      error: () => {
        this.puedeVerWarehouse = false;
      },
    });
}

private habilitarPlanningEnMenuSiAplica(menuPlanning: any): void {
  if (this.menuItems.some((item) => item.label === 'Planeación')) {
    return;
  }

  this.http
    .get<any>(`${environment.apiUrl}/planning/targets/access`)
    .subscribe({
      next: (response) => {
        const puedeVerPlanning = Boolean(
          response?.has_access ??
          response?.hasAccess ??
          response?.can_view ??
          response?.canView ??
          response?.access?.can_view ??
          response?.access?.canView ??
          response?.permissions?.can_view ??
          response?.permissions?.canView
        );

        if (!puedeVerPlanning) {
          return;
        }

        if (this.menuItems.some((item) => item.label === 'Planeación')) {
          return;
        }

        this.puedeVerPlanning = true;
        this.menuItems = [
          ...this.menuItems,
          menuPlanning,
        ];

        this.sincronizarMenuConRutaActual();
      },
      error: () => {
        this.puedeVerPlanning = false;
      },
    });
}

private habilitarInternalDocumentsEnMenuSiAplica(menuNubeCorporativa: any): void {
  if (this.menuItems.some((item) => item.label === 'Nube Corporativa')) {
    return;
  }

  this.http
    .get<any>(`${environment.apiUrl}/internal-documents/access`)
    .subscribe({
      next: (response) => {
        const puedeVerInternalDocuments = Boolean(
          response?.allowed ??
          response?.can_view ??
          response?.canView ??
          response?.has_access ??
          response?.hasAccess ??
          response?.access?.can_view ??
          response?.access?.canView ??
          response?.permissions?.can_view ??
          response?.permissions?.canView
        );

        if (!puedeVerInternalDocuments) {
          return;
        }

        if (this.menuItems.some((item) => item.label === 'Nube Corporativa')) {
          return;
        }

        this.puedeVerInternalDocuments = true;
        this.menuItems = [
          ...this.menuItems,
          menuNubeCorporativa,
        ];

        this.sincronizarMenuConRutaActual();
      },
      error: () => {
        this.puedeVerInternalDocuments = false;
      },
    });
}


  // 🖱️ Lógica de inactividad
  private iniciarTimerInactividad(): void {
    const eventosUsuario = ['mousemove', 'keydown', 'click', 'scroll'];
    eventosUsuario.forEach(evento => {
      window.addEventListener(evento, () => this.reiniciarTimerInactividad());
    });
    this.reiniciarTimerInactividad();
  }


  private reiniciarTimerInactividad(): void {
    if (this.reauthPorInactividadAbierto) {
      return;
    }

    clearTimeout(this.temporizadorInactividad);

    this.temporizadorInactividad = setTimeout(() => {
      this.abrirModalReautenticacion();
    }, this.tiempoInactividad);
  }

  private abrirModalReautenticacion(): void {
    if (this.router.url.includes('/login')) {
      return;
    }

    const reauthYaAbierto = this.dialog.openDialogs.some(
      dialogRef => dialogRef.componentInstance instanceof ReauthModalComponent
    );

    if (this.reauthPorInactividadAbierto || reauthYaAbierto) {
      return;
    }

    this.reauthPorInactividadAbierto = true;
    clearTimeout(this.temporizadorInactividad);

    mostrarAlertaToast('Sesión bloqueada por inactividad. Reautentícate para continuar.');

    const dialogRef = this.dialog.open(ReauthModalComponent, {
      disableClose: true,
      width: '440px',
      maxWidth: '94vw',
      panelClass: 'suite-reauth-dialog',
      backdropClass: 'suite-dialog-backdrop',
      autoFocus: false,
      restoreFocus: false,
    });

    dialogRef.afterClosed().subscribe(result => {
      this.reauthPorInactividadAbierto = false;

      if (result?.token) {
        this.authService.setSession(result.token, result.user || {}, false);
        this.reiniciarTimerInactividad();
        return;
      }

      this.cerrarPorInactividad();
    });
  }

  private cerrarPorInactividad(): void {
    mostrarAlertaToast('Sesión cerrada por inactividad.');
    localStorage.removeItem('token');
    localStorage.removeItem('user');
    this.router.navigate(['/login']);
  }

  ngAfterViewInit(): void {
    this.inicializarIndicador();
  }

ngOnDestroy(): void {
  if (this.validationSummaryIntervalId) {
    clearInterval(this.validationSummaryIntervalId);
    this.validationSummaryIntervalId = null;
  }

  this.validationSummaryRefreshSubscription?.unsubscribe();
}

private verificarRolUsuario(): void {
  const user = this.authService.getUser();
  const rol = (user?.rol || '').toUpperCase();

  this.esAdmin = rol === 'ADMINISTRADOR' || rol === 'SUPER_ADMIN';
  this.esSoloLectura = rol === 'LECTOR_GLOBAL';

  this.puedeVerMantenimientoCompleto =
    rol === 'SISTEMAS' ||
    rol === 'MANTENIMIENTO' ||
    rol === 'ADMINISTRADOR' ||
    rol === 'SUPER_ADMIN';

  this.puedeVerMantenimientoOperativo =
    rol === 'SR_MANTENIMIENTO' ||
    rol === 'AUX_MANTENIMIENTO';

  this.puedeVerMantenimientoGerencial =
    rol === 'GERENTE' ||
    rol === 'GERENTE_REGIONAL';

  this.puedeVerMantenimiento =
    this.puedeVerMantenimientoCompleto ||
    this.puedeVerMantenimientoOperativo ||
    this.puedeVerMantenimientoGerencial;
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
      mostrarAlertaToast('No se especificó un ID de ticket.');
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

  abrirModalReporte() {
    const dialogRef = this.dialog.open(ReportarErrorComponent, {
      width: '400px',
      disableClose: false
    });

    dialogRef.afterClosed().subscribe((resultado) => {
      if (resultado === 'recargar') {
        // Si estamos en la pantalla de tickets, forzar recarga
        if (this.router.url.includes('/main/ver-tickets')) {
          this.router.navigateByUrl('/', { skipLocationChange: true }).then(() => {
            this.router.navigate(['/main/ver-tickets']);
          });
        }
      }
    });
  }

  private sincronizarMenuConRutaActual(): void {
  const currentPath = this.router.url;

  const menuMatch = this.menuItems.find(item => {
    if (item.path === currentPath) {
      return true;
    }

    return Array.isArray(item.submenu)
      && item.submenu.some((sub: { path: string }) => sub.path === currentPath);
  });

  if (menuMatch) {
    this.currentSubmenu = menuMatch.label;
  }
}

private cargarTicketValidationSummary(): void {
  this.ticketService.getValidationSummary().subscribe({
    next: (summary) => {
      this.validationSummary = summary;
    },
    error: () => {
      this.validationSummary = null;
    },
  });
}

private cargarTicketValidationAlertPosition(): void {
  const rawPosition = localStorage.getItem(this.validationAlertPositionKey);

  if (!rawPosition) {
    this.validationAlertPosition = { x: 0, y: 0 };
    return;
  }

  try {
    const parsed = JSON.parse(rawPosition);
    const x = Number(parsed?.x ?? 0);
    const y = Number(parsed?.y ?? 0);

    if (!Number.isFinite(x) || !Number.isFinite(y)) {
      localStorage.removeItem(this.validationAlertPositionKey);
      this.validationAlertPosition = { x, y };
      return;
    }

    this.validationAlertPosition = { x, y };
  } catch {
    localStorage.removeItem(this.validationAlertPositionKey);
    this.validationAlertPosition = { x: 0, y: 0 };
  }
}

get shouldShowValidationAlert(): boolean {
  if (!this.validationSummary) {
    return false;
  }

  if (this.validationSummary.total_por_validar <= 0) {
    return false;
  }

  return !this.isTicketValidationAlertSnoozed();
}

private isTicketValidationAlertSnoozed(): boolean {
  const rawValue = localStorage.getItem(this.validationAlertSnoozeKey);

  if (!rawValue) {
    return false;
  }

  const snoozeUntil = Number(rawValue);

  if (!Number.isFinite(snoozeUntil)) {
    localStorage.removeItem(this.validationAlertSnoozeKey);
    return false;
  }

  if (Date.now() >= snoozeUntil) {
    localStorage.removeItem(this.validationAlertSnoozeKey);
    return false;
  }

  return true;
}

dismissTicketValidationAlert(event: MouseEvent): void {
  event.preventDefault();
  event.stopPropagation();

  const snoozeUntil = Date.now() + this.validationAlertSnoozeMs;
  localStorage.setItem(this.validationAlertSnoozeKey, String(snoozeUntil));
}

onTicketValidationDragStarted(): void {
  this.validationAlertFueArrastrada = false;
}

onTicketValidationDragEnded(event: CdkDragEnd): void {
  const movioEnX = Math.abs(event.distance?.x || 0) > 3;
  const movioEnY = Math.abs(event.distance?.y || 0) > 3;

  this.validationAlertFueArrastrada = movioEnX || movioEnY;

  const freePosition = event.source.getFreeDragPosition();
  this.validationAlertPosition = {
    x: freePosition.x,
    y: freePosition.y,
  };

  localStorage.setItem(
    this.validationAlertPositionKey,
    JSON.stringify(this.validationAlertPosition)
  );
}

goToTicketValidationList(): void {
  if (this.validationAlertFueArrastrada) {
    this.validationAlertFueArrastrada = false;
    return;
  }

  this.currentSubmenu = 'Tickets';
  this.submenuActivo['Tickets'] = 'Ver Tickets';

  this.router.navigate(['/main/ver-tickets'], {
    queryParams: {
      estado: 'por_validar',
    },
  });
}

getTicketValidationIcon(): string {
  if (!this.validationSummary || this.validationSummary.severity === 'normal') {
    return 'assignment_turned_in';
  }

  return 'warning_amber';
}

getTicketValidationTitle(): string {
  if (!this.validationSummary) {
    return 'Por validar';
  }

  if (this.validationSummary.severity === 'critical') {
    return `${this.validationSummary.mayores_72h} críticos`;
  }

  return 'Por validar';
}

getTicketValidationSubtitle(): string {
  if (!this.validationSummary) {
    return 'Clic para revisar';
  }

  if (this.validationSummary.severity === 'critical') {
    return `${this.validationSummary.total_por_validar} pendientes · 72h+`;
  }

  if (this.validationSummary.severity === 'warning') {
    return `${this.validationSummary.mayores_48h} con 48h+`;
  }

  return 'Clic para revisar';
}

onReporteBugDragStarted(): void {
  this.reporteBugFueArrastrado = false;
}

onReporteBugDragEnded(event: any): void {
  const movioEnX = Math.abs(event.distance?.x || 0) > 3;
  const movioEnY = Math.abs(event.distance?.y || 0) > 3;

  this.reporteBugFueArrastrado = movioEnX || movioEnY;
}

onClickReporteBug(): void {
  if (this.reporteBugFueArrastrado) {
    this.reporteBugFueArrastrado = false;
    return;
  }

  this.abrirModalReporte();
}


private puedeVerKpiDesempenoPorRol(): boolean {
  const user = this.authService.getUser();
  const rol = (user?.rol || '').toString().trim().toUpperCase();

  return [
    'ADMIN',
    'ADMINISTRADOR',
    'SUPER_ADMIN',
  ].includes(rol);
}

private puedeVerTrackDiarioPorRol(): boolean {
  const user = this.authService.getUser();
  const rol = (user?.rol || '').toString().trim().toUpperCase();

  return [
    'ADMIN',
    'ADMINISTRADOR',
    'SUPER_ADMIN',
    'LECTOR_GLOBAL',
    'GERENTE',
    'GERENTE_REGIONAL',
    'SISTEMAS',
    "GERENCIA DEPORTIVA",
    'MARKETING',
  ].includes(rol);
}

private puedeVerAperturasPorRol(): boolean {
  const user = this.authService.getUser();
  const rol = (user?.rol || '').toString().trim().toUpperCase();

  return [
    'ADMIN',
    'ADMINISTRADOR',
    'SUPER_ADMIN',
    'SISTEMAS',
    'APERTURAS_ADMIN',
  ].includes(rol);
}


  // ============================================================================
  // Suite Ultra UI v1 - Helpers visuales del menú principal
  // ============================================================================
getMenuIcon(label: string): string {
  const normalizedLabel = String(label || '').toLowerCase();

  const iconsByLabel: Record<string, string> = {
    tickets: 'confirmation_number',
    mantenimiento: 'build',
    inventario: 'inventory_2',
    warehouse: 'warehouse',
    aperturas: 'domain_add',
    'nube corporativa': 'cloud',
    catálogos: 'category',
    catalogos: 'category',
    asistencia: 'event_available',
    permisos: 'admin_panel_settings',
  };

  return iconsByLabel[normalizedLabel] || 'apps';
}

getSubmenuIcon(label: string): string {
  const normalizedLabel = String(label || '').toLowerCase();

  if (normalizedLabel.includes('crear')) {
    return 'add_circle';
  }

  if (normalizedLabel.includes('ver')) {
    return 'visibility';
  }

  if (normalizedLabel.includes('biblioteca') || normalizedLabel.includes('nube')) {
    return 'cloud_queue';
  }

  if (normalizedLabel.includes('track')) {
    return 'monitoring';
  }

  if (normalizedLabel.includes('centro de control') || normalizedLabel.includes('aperturas')) {
    return 'dashboard_customize';
  }

  if (normalizedLabel.includes('promociones') || normalizedLabel.includes('comercial')) {
    return 'campaign';
  }

  if (normalizedLabel.includes('warehouse')) {
    return 'folder_open';
  }

  if (normalizedLabel.includes('bitácora') || normalizedLabel.includes('bitacora')) {
    return 'assignment';
  }

  if (normalizedLabel.includes('historial') || normalizedLabel.includes('consulta')) {
    return 'history';
  }

  if (normalizedLabel.includes('configuración') || normalizedLabel.includes('configuracion')) {
    return 'settings';
  }

  if (normalizedLabel.includes('calendario')) {
    return 'calendar_month';
  }

  if (normalizedLabel.includes('movimientos')) {
    return 'swap_horiz';
  }

  if (normalizedLabel.includes('existencias')) {
    return 'inventory';
  }

  if (normalizedLabel.includes('reportes')) {
    return 'bar_chart';
  }

  if (normalizedLabel.includes('carga')) {
    return 'upload_file';
  }

  if (normalizedLabel.includes('sucursales')) {
    return 'store';
  }

  return 'chevron_right';
}

getSubmenuDescription(label: string): string {
  const normalizedLabel = String(label || '').toLowerCase();

  if (normalizedLabel === 'ver tickets') {
    return 'Consulta y da seguimiento a los tickets registrados.';
  }

  if (normalizedLabel === 'crear ticket') {
    return 'Crea un nuevo ticket para soporte o solicitud.';
  }

  if (normalizedLabel.includes('biblioteca') || normalizedLabel.includes('nube')) {
    return 'Consulta documentos publicados, manuales, políticas y reportes internos.';
  }

  if (normalizedLabel.includes('track')) {
    return 'Consulta indicadores diarios, metas y avance por club.';
  }

  if (normalizedLabel.includes('centro de control') || normalizedLabel.includes('aperturas')) {
    return 'Coordina fases, tareas, responsables, fechas y seguimiento de aperturas.';
  }

  if (normalizedLabel.includes('promociones') || normalizedLabel.includes('comercial')) {
    return 'Analiza promociones por mes, sucursal y desempeño comercial.';
  }

  if (normalizedLabel.includes('warehouse')) {
    return 'Gestiona documentos, reportes y fuentes de información.';
  }

  if (normalizedLabel.includes('bitácora') || normalizedLabel.includes('bitacora')) {
    return 'Captura ejecuciones y evidencias desde operación.';
  }

  if (normalizedLabel.includes('escritorio')) {
    return 'Monitorea activos, programación y avance operativo.';
  }

  if (normalizedLabel.includes('historial') || normalizedLabel.includes('consulta')) {
    return 'Revisa registros históricos y trazabilidad.';
  }

  if (normalizedLabel.includes('configuración') || normalizedLabel.includes('configuracion')) {
    return 'Administra reglas, frecuencias y parámetros.';
  }

  if (normalizedLabel.includes('calendario')) {
    return 'Visualiza programación y actividades por fecha.';
  }

  return 'Acceso rápido al módulo seleccionado.';
}

isMainMenuActive(label: string): boolean {
  return this.currentSubmenu === label;
}

hasVisibleSubmenu(): boolean {
  return this.submenuVisible && this.submenuActual.length > 0;
}

onMainMenuMouseEnter(event: MouseEvent, item: any): void {
  this.cancelarOcultarSubmenu();
  this.moverIndicador(event);
  this.cambiarMenu(item.label);
}

onMainMenuClick(item: any): void {
  this.navegarConCambio(item.path, item.label);
}

  // ============================================================================
  // Fin Suite Ultra UI v1 - Helpers visuales del menú principal
  // ============================================================================
}

