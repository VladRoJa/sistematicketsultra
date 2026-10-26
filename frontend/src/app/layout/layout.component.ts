// src/app/layout/layout.component.ts

import { Component, ElementRef, ViewChild, Renderer2, OnInit, AfterViewInit, OnDestroy } from '@angular/core';
import { Router, RouterModule, RouterOutlet } from '@angular/router';
import { HttpClient, HttpHeaders, HttpErrorResponse } from '@angular/common/http';
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
import { AuthActivityService } from '../core/auth/auth-activity.service';
import { SessionRefreshService } from '../core/auth/session-refresh.service';
import { CdkDragEnd, DragDropModule } from '@angular/cdk/drag-drop';
import { TicketService, TicketValidationSummary } from '../services/ticket.service';
import { AutomationControlService } from '../automation-control/automation-control.service';
import { SchedulerAlertSummary, SchedulerAlertState } from '../automation-control/automation-control.models';
import { Subscription } from 'rxjs';
import { RefrescoService } from '../services/refresco.service';
import { canAccessTrackRegionalOperational } from '../warehouse/track-intelligence-regional-operational/track-regional-operational-access.guard';
import { canAccessContactCenter } from '../contact-center/contact-center-access.guard';
import { withCampaignV2MenuItem } from '../marketing-campaign-v2/marketing-campaign-v2-menu';
import { withPurchaseRequisitionMenuItem } from '../purchase-requisitions/purchase-requisition-menu';
import { SystemDailyCheckGateComponent } from '../system-daily-check/system-daily-check-gate.component';
import { BackgroundDispatchDockComponent } from '../marketing-campaign-v2/background-dispatch-dock.component';

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
    DragDropModule,
    SystemDailyCheckGateComponent,
    BackgroundDispatchDockComponent
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
  readonly maxMainMenuItems = 10;

private readonly mainMenuPriority: string[] = [
  'Control',
  'Sistemas',
  'Tickets',
  'Contact Center',
  'Mantenimiento',
  'Inventario',
  'Track',
  'Aperturas',
  'Automatización',
  'Análisis Deportivo',
  'Marketing y Conversión',
  'Warehouse',
  'Planeación',
];

get menuItemsPrincipales(): any[] {
  const priorityByLabel = new Map(
    this.mainMenuPriority.map((label, index) => [label, index])
  );

  return [...this.menuItems]
    .sort((a, b) => {
      const priorityA = priorityByLabel.get(a.label) ?? Number.MAX_SAFE_INTEGER;
      const priorityB = priorityByLabel.get(b.label) ?? Number.MAX_SAFE_INTEGER;

      return priorityA - priorityB;
    })
    .slice(0, this.maxMainMenuItems);
}

get menuItemsAdicionales(): any[] {
  const labelsPrincipales = new Set(
    this.menuItemsPrincipales.map((item) => item.label)
  );

  return this.menuItems.filter(
    (item) => !labelsPrincipales.has(item.label)
  );
}

get hayMenuAdicional(): boolean {
  return this.menuItemsAdicionales.length > 0;
}

get puedeVerAccionesFlotantesGlobales(): boolean {
  const user = this.authService.getUser();
  const username = String(
    user?.username ?? ''
  ).trim().toUpperCase();

  return username !== 'ADMICORP';
}

isMoreMenuActive(): boolean {
  return this.menuItemsAdicionales.some(
    (item) => item.label === this.currentSubmenu
  );
}
  esCoordinadorMantenimiento = false;
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

  automationAlertSummary: SchedulerAlertSummary | null = null;
  automationAlertUnavailable = false;
  automationAlertPosition = { x: 0, y: 0 };
  automationAlertFueArrastrada = false;
  private automationAlertLoading = false;
  private automationAlertIntervalId: ReturnType<typeof setInterval> | null = null;
  private automationAlertSubscription?: Subscription;
  private readonly automationAlertRefreshMs = 60 * 1000;
  private readonly automationAlertSnoozeMs = 3 * 60 * 1000;
  private readonly automationAlertSnoozeKey = 'suite.automationAlert.snooze';
  private readonly automationAlertPositionKey = 'suite.automationAlert.position';

  private apiUrl = `${environment.apiUrl}/tickets`;

  // ⏳ Configuración de inactividad
  private tiempoInactividad = 45 * 60 * 1000; // 45 minutos en ms
  private temporizadorInactividad: ReturnType<typeof setTimeout> | null = null;
  private reauthPorInactividadAbierto = false;
  private readonly eventosActividad = [
    'pointermove', 'pointerdown', 'keydown', 'touchstart', 'wheel', 'scroll'
  ];
  private ultimoChequeoRefreshAt = 0;
  private readonly escucharActividadHumana = (event: Event): void => {
    if (!event.isTrusted || this.reauthPorInactividadAbierto) return;
    this.activity.recordInteraction();
    this.reiniciarTimerInactividad();
    this.verificarRenovacionSilenciosa();
  };
  private readonly comprobarActividadExterna = (): void => {
    this.reiniciarTimerInactividad();
    this.verificarRenovacionSilenciosa();
  };
  private readonly onAuthStorageChange = (event: StorageEvent): void => {
    if (event.key === 'token' && !event.newValue) {
      // Logout in another tab is not inactivity: go straight to login.
      this.activity.clear();
      this.router.navigate(['/login']);
      return;
    }
    if (event.key === this.activity.storageKey || event.key === 'token') {
      this.comprobarActividadExterna();
    }
  };

  constructor(
    private router: Router,
    private http: HttpClient,
    private dialog: MatDialog,
    private renderer: Renderer2,
    private authService: AuthService,
    private inactividadService: InactividadService,
    private session: SessionService,
    private activity: AuthActivityService,
    private refreshSesion: SessionRefreshService,
    private ticketService: TicketService,
    private refrescoService: RefrescoService,
    private automationControlService: AutomationControlService,
  ) {}

ngOnInit(): void {
  this.verificarRolUsuario();
  const u = this.session.getUser();
  this.usuarioLabel = (u?.username || '').toString();
  this.iniciarTimerInactividad();
  this.inactividadService.registrarCallback(() => this.reiniciarTimerInactividad());
  const menuControl = {
    label: 'Control',
    path: '/control',
    submenu: [
      { label: 'Centro de Control', path: '/control' },
    ],
  };

  const menuSistemas = {
    label: 'Sistemas',
    path: '/sistemas/salud',
    submenu: [
      { label: 'Salud de Sistemas', path: '/sistemas/salud' },
    ],
  };

  const menuContactCenter = {
    label: 'Contact Center',
    path: '/contact-center',
    submenu: [
      { label: 'Operación Contact Center', path: '/contact-center' },
    ],
  };

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

  if (
    canAccessTrackRegionalOperational(
      this.authService.getUser()
    )
  ) {
    trackSubmenu.push({
      label: 'Seguimiento regional',
      path: '/warehouse/track-intelligence/regional-operational',
    });
  }

  if (this.puedeVerKpiDesempenoPorRol()) {
    trackSubmenu.push({
      label: 'KPI Desempeño',
      path: '/warehouse/track/kpi-desempeno',
    });
  }

  if (this.puedeVerTrackForecastBeta()) {
    trackSubmenu.push({
      label: 'Proyección y Metas',
      path: '/warehouse/track/forecast',
    });
  }

  if (this.puedeVerTrackForecastCenterPorRol()) {
    trackSubmenu.push({
      label: 'Centro de Forecast',
      path: '/warehouse/track/forecast-center',
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

  const menuAutomatizacion = {
    label: 'Automatización',
    path: '/rpa/gasca-sms',
    submenu: [
      { label: 'Códigos Gasca SMS', path: '/rpa/gasca-sms' },
    ],
  };

  const sportsAnalysisUser = this.authService.getUser();
  const sportsAnalysisUsername = String(
    sportsAnalysisUser?.username ?? ''
  ).trim().toUpperCase();
  const sportsAnalysisRole = String(
    sportsAnalysisUser?.rol ?? sportsAnalysisUser?.role ?? ''
  ).trim().toUpperCase();

  const sportsAnalysisSubmenu: Array<{ label: string; path: string }> = [];

  if (this.puedeVerControlRutinasPorRol()) {
    sportsAnalysisSubmenu.push({
      label: 'Control de Rutinas',
      path: '/control-rutinas',
    });
  }

  if (
    sportsAnalysisUsername === 'ADMICORP'
    || sportsAnalysisRole === 'GERENCIA DEPORTIVA'
    || sportsAnalysisRole === 'GERENTE'
    || sportsAnalysisRole === 'GERENTE_REGIONAL'
  ) {
    sportsAnalysisSubmenu.push({
      label: 'Aforo y Asistencia',
      path: '/analisis-deportivo/aforo-asistencia',
    });
  }

  const menuAnalisisDeportivo = {
    label: 'Análisis Deportivo',
    path: sportsAnalysisSubmenu[0]?.path || '/main/ver-tickets',
    submenu: sportsAnalysisSubmenu,
  };

  const marketingConversionSubmenu: Array<{ label: string; path: string }> = [];
  const marketingUsername = String(
    this.authService.getUser()?.username ?? ''
  ).trim().toUpperCase();

  if (marketingUsername === 'ADMICORP') {
    marketingConversionSubmenu.push({
      label: 'Embudo mensual',
      path: '/marketing-conversion',
    });
  }

  if (this.puedeVerMarketingSalesFunnelPorRol()) {
    marketingConversionSubmenu.push(
      {
        label: 'Funnel Venta Nueva · Original',
        path: '/marketing-conversion/venta-total-original',
      },
      {
        label: 'Funnel Venta Nueva · Ajustado',
        path: '/marketing-conversion/venta-total',
      },
    );
  }

  if (this.esAdmin) {
    marketingConversionSubmenu.push({
      label: 'Google Ads · Administración',
      path: '/marketing/google-ads',
    });
  }

  const menuMarketingConversion = {
    label: 'Marketing y Conversión',
    path: marketingConversionSubmenu[0]?.path || '/main/ver-tickets',
    submenu: marketingConversionSubmenu,
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

  const menuMantenimientoCoordinador = [
    {
      label: 'Tickets',
      path: '/main/ver-tickets',
      submenu: [
        { label: 'Ver Tickets', path: '/main/ver-tickets' },
        { label: 'Crear Ticket', path: '/main/crear-ticket' },
      ],
    },
    {
      label: 'Mantenimiento',
      path: '/maintenance-planner',
      submenu: [
        { label: 'Planner de Mantenimiento', path: '/maintenance-planner' },
        { label: 'Consulta / Historial', path: '/pm/consulta-historial' },
        { label: 'Calendario', path: '/pm/calendario' },
      ],
    },
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
  } else if (this.esCoordinadorMantenimiento) {
    this.menuItems = menuMantenimientoCoordinador;
  } else {
    this.menuItems = soloTickets;
  }

// El perfil exclusivo de coordinación no publica otros módulos dinámicos.
if (!this.esCoordinadorMantenimiento) {
this.habilitarControlEnMenuSiAplica(menuControl);
this.habilitarSistemasEnMenuSiAplica(menuSistemas);
this.habilitarContactCenterEnMenuSiAplica(menuContactCenter);
this.habilitarPurchaseRequisitionsEnMenuSiAplica();
this.habilitarMaintenancePlannerEnMenu();
this.habilitarMantenimientoComprasEnMenuSiAplica();

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

if (
  this.puedeVerGascaSmsPorRol() &&
  !this.menuItems.some((item) => item.label === 'Automatización')
) {
  this.menuItems = [
    ...this.menuItems,
    menuAutomatizacion,
  ];
}

if (
  sportsAnalysisSubmenu.length > 0
  && !this.menuItems.some(
    (item) => item.label === 'Análisis Deportivo'
  )
) {
  this.menuItems = [
    ...this.menuItems,
    menuAnalisisDeportivo,
  ];
}

if (
  this.puedeVerMarketingConversionPorRol() &&
  !this.menuItems.some((item) => item.label === 'Marketing y Conversión')
) {
  this.menuItems = [
    ...this.menuItems,
    menuMarketingConversion,
  ];
}

this.habilitarWarehouseEnMenuSiAplica(menuWarehouse);
  this.habilitarPlanningEnMenuSiAplica(menuPlanning);
  this.habilitarCampaignV2EnMenuSiAplica();
  this.habilitarInternalDocumentsEnMenuSiAplica(menuNubeCorporativa);
  this.habilitarPermisosObservabilidadEnMenuSiAplica();
  this.habilitarAdminUsuariosEnMenuSiAplica();
}
  this.sincronizarMenuConRutaActual();

  if (this.puedeVerAccionesFlotantesGlobales) {
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

  if (this.puedeVerAlertaAutomatizaciones) {
    this.cargarAutomationAlertPosition();
    this.cargarAutomationAlerts();
    this.automationAlertIntervalId = setInterval(
      () => this.cargarAutomationAlerts(), this.automationAlertRefreshMs
    );
  }
  }

private habilitarControlEnMenuSiAplica(menuControl: any): void {
  if (this.menuItems.some((item) => item.label === 'Control')) {
    return;
  }

  this.http
    .get<any>(`${environment.apiUrl}/control/context`)
    .subscribe({
      next: () => {
        if (this.menuItems.some((item) => item.label === 'Control')) {
          return;
        }

        this.menuItems = [menuControl, ...this.menuItems];
        this.sincronizarMenuConRutaActual();
      },
      error: () => {
        // El backend es la autoridad. Si responde 401/403 no se publica el menú.
      },
    });
}

private habilitarSistemasEnMenuSiAplica(menuSistemas: any): void {
  if (this.menuItems.some((item) => item.label === 'Sistemas')) {
    return;
  }

  this.http
    .get<any>(`${environment.apiUrl}/system-daily-checks/bi/context`)
    .subscribe({
      next: (response) => {
        if (!response?.allowed) {
          return;
        }

        if (this.menuItems.some((item) => item.label === 'Sistemas')) {
          return;
        }

        const isAdmicorp = String(this.session.getUser()?.username || '').trim().toUpperCase() === 'ADMICORP';
        if (isAdmicorp) {
          menuSistemas.submenu.push({ label: 'Control de Automatizaciones', path: '/sistemas/automatizaciones' });
        }
        this.menuItems = [
          ...this.menuItems,
          menuSistemas,
        ];
        this.sincronizarMenuConRutaActual();
      },
      error: () => {
        // El backend es la autoridad del rollout MVP.
      },
    });
}

private habilitarContactCenterEnMenuSiAplica(menuContactCenter: any): void {
  const user = this.session.getUser();

  if (!canAccessContactCenter(user)) {
    return;
  }

  if (this.menuItems.some((item) => item.label === 'Contact Center')) {
    return;
  }

  this.http
    .get<any>(`${environment.apiUrl}/contact-center/access`)
    .subscribe({
      next: (response) => {
        if (!response?.allowed) {
          return;
        }

        if (this.menuItems.some((item) => item.label === 'Contact Center')) {
          return;
        }

        this.menuItems = [
          ...this.menuItems,
          menuContactCenter,
        ];
        this.sincronizarMenuConRutaActual();
      },
      error: () => {
        // El backend es la autoridad. Si responde 401/403 no se publica el menú.
      },
    });
}

private habilitarPurchaseRequisitionsEnMenuSiAplica(): void {
  this.http
    .get<{ allowed?: boolean }>(`${environment.apiUrl}/purchase-requisitions/access`)
    .subscribe({
      next: (response) => {
        if (!response?.allowed) {
          return;
        }

        const nextMenuItems = withPurchaseRequisitionMenuItem(this.menuItems);
        if (nextMenuItems === this.menuItems) {
          return;
        }

        this.menuItems = nextMenuItems;
        this.sincronizarMenuConRutaActual();
      },
      error: () => {
        // Backend-authoritative: 401/403 no publica Requisiciones.
      },
    });
}

private habilitarMantenimientoComprasEnMenuSiAplica(): void {
  const rol = String(this.session.getUser()?.rol || '').trim().toUpperCase();
  if (rol !== 'COMPRAS') {
    return;
  }

  this.http
    .get<{ allowed?: boolean }>(`${environment.apiUrl}/pm/access`)
    .subscribe({
      next: (response) => {
        if (!response?.allowed || this.menuItems.some((item) => item.label === 'Mantenimiento')) {
          return;
        }

        this.menuItems = [
          ...this.menuItems,
          {
            label: 'Mantenimiento',
            path: '/maintenance-planner',
            submenu: [
              { label: 'Planner de Mantenimiento', path: '/maintenance-planner' },
              { label: 'Consulta / Historial', path: '/pm/consulta-historial' },
              { label: 'Calendario', path: '/pm/calendario' },
            ],
          },
        ];
        this.sincronizarMenuConRutaActual();
      },
      error: () => {
        // Sin autorización explícita del backend no se publica el menú.
      },
    });
}

private habilitarMaintenancePlannerEnMenu(): void {
  if (!this.puedeVerMaintenancePlannerPorRol()) {
    return;
  }

  const plannerItem = {
    label: 'Planner de Mantenimiento',
    path: '/maintenance-planner',
  };

  const mantenimientoMenu = this.menuItems.find(
    (item) => item.label === 'Mantenimiento'
  );

  if (!mantenimientoMenu) {
    this.menuItems = [
      ...this.menuItems,
      {
        label: 'Mantenimiento',
        path: '/maintenance-planner',
        submenu: [plannerItem],
      },
    ];
    this.sincronizarMenuConRutaActual();
    return;
  }

  const submenu = Array.isArray(mantenimientoMenu.submenu)
    ? mantenimientoMenu.submenu
    : [];

  if (submenu.some((item: { path: string }) => item.path === plannerItem.path)) {
    return;
  }

  const nextSubmenu = [...submenu];
  const escritorioIndex = nextSubmenu.findIndex(
    (item: { path: string }) => item.path === '/pm/escritorio-preventivo'
  );
  const insertIndex = escritorioIndex >= 0 ? escritorioIndex + 1 : 0;
  nextSubmenu.splice(insertIndex, 0, plannerItem);
  mantenimientoMenu.submenu = nextSubmenu;
  this.sincronizarMenuConRutaActual();
}

private puedeVerMaintenancePlannerPorRol(): boolean {
  const user = this.authService.getUser();
  const rol = String(user?.rol ?? user?.role ?? '').trim().toUpperCase();

  return [
    'ADMIN',
    'ADMINISTRADOR',
    'SUPER_ADMIN',
    'MANTENIMIENTO',
    'SR_MANTENIMIENTO',
    'AUX_MANTENIMIENTO',
    'COORDINADOR_MANTENIMIENTO',
    'SISTEMAS',
    'TECNICO',
    'GERENTE',
    'GERENTE_REGIONAL',
    'LECTOR_GLOBAL',
  ].includes(rol);
}

private habilitarAdminUsuariosEnMenuSiAplica(): void {
  const user = this.session.getUser();
  const username = String(user?.username || '').trim().toUpperCase();

  if (username !== 'ADMICORP') {
    return;
  }

  const alreadyExists = this.menuItems.some(
    (item) => item.path === '/admin/usuarios'
  );

  if (alreadyExists) {
    return;
  }

  this.menuItems = [
    ...this.menuItems,
    {
      label: 'Administrar usuarios',
      path: '/admin/usuarios',
    },
  ];
}

private habilitarPermisosObservabilidadEnMenuSiAplica(): void {
  const user = this.session.getUser();
  const rol = (user?.rol || '').toString().trim().toUpperCase();

  if (!['ADMIN', 'ADMINISTRADOR', 'SUPER_ADMIN'].includes(rol)) {
    return;
  }

  const observabilitySubmenu = {
    label: 'Observabilidad de permisos',
    path: '/admin/permisos-observabilidad',
  };

  const permisosMenu = this.menuItems.find((item) => item.label === 'Permisos');

  if (permisosMenu) {
    const submenu = Array.isArray(permisosMenu.submenu) ? permisosMenu.submenu : [];
    const alreadyExists = submenu.some(
      (item: { path: string }) => item.path === observabilitySubmenu.path
    );

    if (!alreadyExists) {
      permisosMenu.submenu = [
        ...submenu,
        observabilitySubmenu,
      ];
    }

    return;
  }

  this.menuItems = [
    ...this.menuItems,
    {
      label: 'Permisos',
      path: '/admin/permisos-observabilidad',
      submenu: [
        observabilitySubmenu,
      ],
    },
  ];

  this.sincronizarMenuConRutaActual();
}

private habilitarCampaignV2EnMenuSiAplica(): void {
  const alreadyPublished = this.menuItems.some(
    (menu) => Array.isArray(menu.submenu)
      && menu.submenu.some(
        (item: { path?: string }) => item.path === '/marketing/campaigns-v2'
      )
  );

  if (alreadyPublished) {
    return;
  }

  this.http
    .get<unknown>(`${environment.apiUrl}/marketing/campaigns-v2/options`)
    .subscribe({
      next: () => {
        const nextMenuItems = withCampaignV2MenuItem(this.menuItems);
        if (nextMenuItems === this.menuItems) {
          return;
        }
        this.menuItems = nextMenuItems;
        this.sincronizarMenuConRutaActual();
      },
      error: () => {
        // Backend-authoritative: 401/403 no publica Campañas V2.
      },
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


  // El reloj se calcula contra actividad humana real, no contra polling.
  private iniciarTimerInactividad(): void {
    this.activity.initializeIfAbsent();
    this.eventosActividad.forEach(evento => {
      // Captura incluso scroll dentro de contenedores Angular Material.
      window.addEventListener(evento, this.escucharActividadHumana, true);
    });
    window.addEventListener('focus', this.comprobarActividadExterna);
    window.addEventListener('storage', this.onAuthStorageChange);
    document.addEventListener('visibilitychange', this.comprobarActividadExterna);
    this.reiniciarTimerInactividad();
  }

  private reiniciarTimerInactividad(): void {
    if (this.temporizadorInactividad) {
      clearTimeout(this.temporizadorInactividad);
      this.temporizadorInactividad = null;
    }
    if (this.reauthPorInactividadAbierto) return;

    const restante = this.activity.millisecondsUntilIdle(this.tiempoInactividad);
    if (restante <= 0) {
      this.abrirModalReautenticacion();
      return;
    }
    // Recalcular periódicamente por cambios en otras pestañas y pestañas
    // suspendidas: nunca extender 45 minutos por una solicitud automática.
    this.temporizadorInactividad = setTimeout(
      () => {
        this.reiniciarTimerInactividad();
        this.verificarRenovacionSilenciosa();
      },
      Math.min(restante, 30 * 1000),
    );
  }

  private verificarRenovacionSilenciosa(): void {
    if (this.reauthPorInactividadAbierto || this.activity.isLocked()) return;
    const ahora = Date.now();
    if (ahora - this.ultimoChequeoRefreshAt < 15 * 1000) return;

    const token = this.session.getToken();
    if (!token || !this.refreshSesion.shouldRenewSoon(token)) return;
    this.ultimoChequeoRefreshAt = ahora;
    this.refreshSesion.renewIfNeeded(token).catch(error => {
      // A revoked/expired refresh session cannot be silently resumed.
      // Never print credentials or entire backend auth responses.
      if (error?.status === 401 && !this.activity.isLocked()) {
        this.authService.logout();
      }
    });
  }

  private abrirModalReautenticacion(): void {
    if (this.router.url.includes('/login')) return;
    const reauthYaAbierto = this.dialog.openDialogs.some(
      dialogRef => dialogRef.componentInstance instanceof ReauthModalComponent
    );
    if (this.reauthPorInactividadAbierto || reauthYaAbierto) return;

    this.reauthPorInactividadAbierto = true;
    this.activity.lock();
    if (this.temporizadorInactividad) {
      clearTimeout(this.temporizadorInactividad);
      this.temporizadorInactividad = null;
    }

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
      if (result?.token && result?.user) {
        this.authService.setSession(result.token, result.user, false);
        this.activity.unlock();
        this.activity.recordInteraction();
        this.reiniciarTimerInactividad();
        return;
      }
      this.cerrarPorInactividad();
    });
  }

  private cerrarPorInactividad(): void {
    mostrarAlertaToast('Sesión cerrada por inactividad.');
    this.authService.logout();
  }

  ngAfterViewInit(): void {
    this.inicializarIndicador();
  }

ngOnDestroy(): void {
  if (this.temporizadorInactividad) {
    clearTimeout(this.temporizadorInactividad);
    this.temporizadorInactividad = null;
  }
  this.eventosActividad.forEach(evento => {
    window.removeEventListener(evento, this.escucharActividadHumana, true);
  });
  window.removeEventListener('focus', this.comprobarActividadExterna);
  window.removeEventListener('storage', this.onAuthStorageChange);
  document.removeEventListener('visibilitychange', this.comprobarActividadExterna);
  this.inactividadService.registrarCallback(null);
  if (this.validationSummaryIntervalId) {
    clearInterval(this.validationSummaryIntervalId);
    this.validationSummaryIntervalId = null;
  }

  this.validationSummaryRefreshSubscription?.unsubscribe();
  if (this.automationAlertIntervalId) {
    clearInterval(this.automationAlertIntervalId);
    this.automationAlertIntervalId = null;
  }
  this.automationAlertSubscription?.unsubscribe();
}

private verificarRolUsuario(): void {
  const user = this.authService.getUser();
  const rol = (user?.rol || '').toUpperCase();

  this.esCoordinadorMantenimiento = rol === 'COORDINADOR_MANTENIMIENTO';
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
    this.authService.logout();
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
    if (this.currentSubmenu === 'Más') {
      this.currentSubmenu = label;
      this.router.navigateByUrl(path);
      return;
    }

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
    }, 700);
  }

  cancelarOcultarSubmenu(): void {
    if (this.ocultarTimeout) {
      clearTimeout(this.ocultarTimeout);
    }
  }

  get submenuActual() {
    if (this.currentSubmenu === 'Más') {
      return this.menuItemsAdicionales;
    }

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

get puedeVerAlertaAutomatizaciones(): boolean {
  return String(this.session.getUser()?.username ?? '').trim().toUpperCase() === 'ADMICORP';
}

private cargarAutomationAlerts(): void {
  if (this.automationAlertLoading) {
    return;
  }
  this.automationAlertLoading = true;
  this.automationAlertSubscription = this.automationControlService.alertSummary().subscribe({
    next: (summary) => {
      this.automationAlertSummary = summary;
      this.automationAlertUnavailable = false;
      this.automationAlertLoading = false;
    },
    error: (error: HttpErrorResponse) => {
      this.automationAlertSummary = null;
      // A denied request is not evidence of a scheduler failure.
      this.automationAlertUnavailable = error.status !== 401 && error.status !== 403;
      this.automationAlertLoading = false;
    },
  });
}

private cargarAutomationAlertPosition(): void {
  const raw = localStorage.getItem(this.automationAlertPositionKey);
  if (!raw) {
    return;
  }
  try {
    const value = JSON.parse(raw);
    const x = Number(value?.x);
    const y = Number(value?.y);
    if (!Number.isFinite(x) || !Number.isFinite(y)) {
      throw new Error('Invalid position');
    }
    this.automationAlertPosition = { x, y };
  } catch {
    localStorage.removeItem(this.automationAlertPositionKey);
    this.automationAlertPosition = { x: 0, y: 0 };
  }
}

get automationAlertSeverity(): SchedulerAlertState {
  return this.automationAlertUnavailable ? 'WARNING' : this.automationAlertSummary?.state ?? 'CLEAR';
}

get automationAlertCount(): number {
  return this.automationAlertSummary?.issue_count ?? 0;
}

get automationAlertFingerprint(): string {
  const issues = this.automationAlertSummary?.issues ?? [];
  return issues.length
    ? issues.map(issue => issue.key + ':' + issue.severity + ':' + issue.reason_code).sort().join('|')
    : this.automationAlertUnavailable ? 'MONITOR_UNAVAILABLE' : '';
}

private isAutomationAlertSnoozed(): boolean {
  const raw = localStorage.getItem(this.automationAlertSnoozeKey);
  if (!raw) {
    return false;
  }
  try {
    const saved = JSON.parse(raw);
    const until = Number(saved?.until);
    if (!Number.isFinite(until) || typeof saved?.fingerprint !== 'string') {
      throw new Error('Invalid snooze');
    }
    if (Date.now() < until && saved.fingerprint === this.automationAlertFingerprint) {
      return true;
    }
    if (Date.now() >= until) {
      localStorage.removeItem(this.automationAlertSnoozeKey);
    }
  } catch {
    localStorage.removeItem(this.automationAlertSnoozeKey);
  }
  return false;
}

get shouldShowAutomationAlert(): boolean {
  if (!this.puedeVerAlertaAutomatizaciones) {
    return false;
  }
  if (!this.automationAlertUnavailable && this.automationAlertCount === 0) {
    return false;
  }
  return !this.isAutomationAlertSnoozed();
}

get automationAlertTitle(): string {
  return this.automationAlertUnavailable
    ? 'Monitoreo no disponible'
    : this.automationAlertSeverity === 'CRITICAL'
      ? 'Fallos en automatizaciones' : 'Automatizaciones en revisión';
}

get automationAlertSubtitle(): string {
  const count = this.automationAlertCount;
  return this.automationAlertUnavailable
    ? 'No se pudo verificar la salud'
    : count + (count === 1 ? ' incidencia detectada' : ' incidencias detectadas');
}

dismissAutomationAlert(event: MouseEvent): void {
  event.preventDefault();
  event.stopPropagation();
  localStorage.setItem(this.automationAlertSnoozeKey, JSON.stringify({
    until: Date.now() + this.automationAlertSnoozeMs,
    fingerprint: this.automationAlertFingerprint,
  }));
}

onAutomationAlertDragStarted(): void {
  this.automationAlertFueArrastrada = false;
}

onAutomationAlertDragEnded(event: CdkDragEnd): void {
  this.automationAlertFueArrastrada =
    Math.abs(event.distance?.x || 0) > 3 || Math.abs(event.distance?.y || 0) > 3;
  const position = event.source.getFreeDragPosition();
  this.automationAlertPosition = { x: position.x, y: position.y };
  localStorage.setItem(
    this.automationAlertPositionKey, JSON.stringify(this.automationAlertPosition)
  );
}

goToAutomationControl(): void {
  if (this.automationAlertFueArrastrada) {
    this.automationAlertFueArrastrada = false;
    return;
  }
  this.currentSubmenu = 'Sistemas';
  this.submenuActivo['Sistemas'] = 'Control de Automatizaciones';
  this.router.navigate(['/sistemas/automatizaciones']);
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
  if (!this.puedeVerAccionesFlotantesGlobales) {
    return false;
  }

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


private puedeVerTrackForecastBeta(): boolean {
  const user = this.authService.getUser();
  const userId = Number(user?.id ?? user?.user_id ?? user?.usuario_id ?? 0);
  const rol = String(user?.rol ?? user?.role ?? '').trim().toUpperCase();

  if (rol === 'LECTOR_GLOBAL') {
    return true;
  }

  return userId === 47;
}

private puedeVerTrackForecastCenterPorRol(): boolean {
  const user = this.authService.getUser();
  const rol = String(user?.rol ?? user?.role ?? '').trim().toUpperCase();

  return [
    'ADMIN',
    'ADMINISTRADOR',
    'SUPER_ADMIN',
    'LECTOR_GLOBAL',
    'GERENTE',
    'GERENTE_REGIONAL',
  ].includes(rol);
}

private puedeVerKpiDesempenoPorRol(): boolean {
  const user = this.authService.getUser();
  const rol = (user?.rol || '').toString().trim().toUpperCase();

  return [
    'ADMIN',
    'ADMINISTRADOR',
    'SUPER_ADMIN',
    'LECTOR_GLOBAL',
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
    'TIENDA',
  ].includes(rol);
}

private puedeVerGascaSmsPorRol(): boolean {
  const user = this.authService.getUser();
  const rol = (user?.rol || '').toString().trim().toUpperCase();

  return [
    'ADMIN',
    'ADMINISTRADOR',
    'SUPER_ADMIN',
    'GERENTE',
    'SISTEMAS',
    'GERENTE_REGIONAL',

  ].includes(rol);
}

private puedeVerControlRutinasPorRol(): boolean {
  const user = this.authService.getUser();
  const rol = String(user?.rol ?? user?.role ?? '').trim().toUpperCase();

  return [
    'ADMIN',
    'ADMINISTRADOR',
    'SUPER_ADMIN',
    'LECTOR_GLOBAL',
    'GERENTE',
    'GERENTE_REGIONAL',
    'GERENCIA DEPORTIVA',
  ].includes(rol);
}

private puedeVerMarketingSalesFunnelPorRol(): boolean {
  const user = this.authService.getUser();
  const rol = String(user?.rol ?? user?.role ?? '').trim().toUpperCase();
  const username = String(user?.username ?? '').trim().toUpperCase();

  return (
    username === 'ADMICORP'
    || rol === 'LECTOR_GLOBAL'
    || rol === 'GERENTE'
    || rol === 'GERENTE_REGIONAL'
    || rol === 'MARKETING'
  );
}

private puedeVerMarketingConversionPorRol(): boolean {
  return (
    this.puedeVerMarketingSalesFunnelPorRol()
    || this.puedeVerMarketingReactivacionPorRol()
  );
}

private puedeVerMarketingReactivacionPorRol(): boolean {
  const user = this.authService.getUser();
  const rol = String(user?.rol ?? user?.role ?? '').trim().toUpperCase();
  const username = String(user?.username ?? '').trim().toUpperCase();

  if (username === 'ADMICORP') {
    return true;
  }

  return [
    'ADMIN',
    'ADMINISTRADOR',
    'SUPER_ADMIN',
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
    control: 'dashboard',
    sistemas: 'health_and_safety',
    tickets: 'confirmation_number',
    mantenimiento: 'build',
    inventario: 'inventory_2',
    warehouse: 'warehouse',
    aperturas: 'domain_add',
    automatización: 'smart_toy',
    automatizacion: 'smart_toy',
    'nube corporativa': 'cloud',
    catálogos: 'category',
    catalogos: 'category',
    permisos: 'admin_panel_settings',
    'control de rutinas': 'assignment_turned_in',
    'marketing y conversión': 'campaign',
    'contact center': 'support_agent',
  };

  return iconsByLabel[normalizedLabel] || 'apps';
}

getSubmenuIcon(label: string): string {
  const normalizedLabel = String(label || '').toLowerCase();

  if (normalizedLabel.includes('salud de sistemas')) {
    return 'health_and_safety';
  }

  if (normalizedLabel.includes('planner')) {
    return 'event_note';
  }

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

  if (normalizedLabel.includes('contact center')) {
    return 'support_agent';
  }

  if (normalizedLabel.includes('marketing')) {
    return 'campaign';
  }

  if (normalizedLabel.includes('reactivación')) {
    return 'person_search';
  }

  if (
    normalizedLabel.includes('códigos gasca') ||
    normalizedLabel.includes('codigos gasca') ||
    normalizedLabel.includes('sms')
  ) {
    return 'sms';
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

  if (normalizedLabel.includes('resumen operativo')) {
    return 'dashboard';
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

  if (normalizedLabel.includes('salud de sistemas')) {
    return 'Revisa cumplimiento, fallas, recurrencia y trazabilidad del checklist diario.';
  }

  if (normalizedLabel.includes('planner')) {
    return 'Agenda tickets de mantenimiento, revisa compromisos y reprograma trabajos.';
  }

  if (normalizedLabel.includes('biblioteca') || normalizedLabel.includes('nube')) {
    return 'Consulta documentos publicados, manuales, políticas y reportes internos.';
  }

  if (normalizedLabel.includes('track')) {
    return 'Consulta indicadores diarios, metas y avance por club.';
  }

  if (normalizedLabel.includes('contact center')) {
    return 'Trabaja cartera, seguimientos y citas comerciales.';
  }

  if (normalizedLabel.includes('marketing')) {
    return 'Consulta el embudo mensual de leads, visitas y ventas atribuidas.';
  }

  if (
    normalizedLabel.includes('códigos gasca') ||
    normalizedLabel.includes('codigos gasca') ||
    normalizedLabel.includes('sms')
  ) {
    return 'Consulta Gasca, valida el código y deja bitácora del resultado.';
  }

  if (normalizedLabel === 'centro de control') {
    return 'Resume señales ejecutivas y permite bajar hasta su fuente.';
  }

  if (normalizedLabel.includes('aperturas')) {
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
