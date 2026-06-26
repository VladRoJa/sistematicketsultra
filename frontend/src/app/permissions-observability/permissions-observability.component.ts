// frontend/src/app/permissions-observability/permissions-observability.component.ts

import { CommonModule } from '@angular/common';
import { Component, OnInit } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { finalize, forkJoin } from 'rxjs';

import { SessionService } from '../core/auth/session.service';
import {
  EffectivePermissionAction,
  EffectivePermissionResponse,
  PermissionAction,
  PermissionModule,
  PermissionRouteMap,
  PermissionsObservabilityService,
} from './permissions-observability.service';

type PermissionsTab = 'modules' | 'actions' | 'routes' | 'effective';

interface SummaryCard {
  label: string;
  value: string;
  tone: 'neutral' | 'success' | 'warning' | 'danger';
}

@Component({
  selector: 'app-permissions-observability',
  standalone: true,
  imports: [
    CommonModule,
    FormsModule,
  ],
  templateUrl: './permissions-observability.component.html',
  styleUrls: ['./permissions-observability.component.css'],
})
export class PermissionsObservabilityComponent implements OnInit {
  readonly pageTitle = 'Observabilidad de permisos';
  readonly pageSubtitle =
    'Consulta módulos, acciones, rutas high-risk y permisos efectivos por usuario. Esta vista es solo diagnóstico.';

  activeTab: PermissionsTab = 'modules';

  modules: PermissionModule[] = [];
  actions: PermissionAction[] = [];
  routes: PermissionRouteMap[] = [];

  selectedModuleKey = '';
  selectedRiskLevel = '';
  selectedReviewStatus = '';
  showInactiveRoutes = true;

  userIdInput = '';
  effectivePermissions: EffectivePermissionResponse | null = null;

  isLoadingCatalog = false;
  isLoadingEffective = false;
  errorMessage = '';

  constructor(
    private readonly permissionsService: PermissionsObservabilityService,
    private readonly session: SessionService,
  ) {}

  ngOnInit(): void {
    const currentUser = this.session.getUser();
    this.userIdInput = currentUser?.id ? String(currentUser.id) : '';

    this.loadCatalog();

    if (this.userIdInput) {
      this.loadEffectivePermissions();
    }
  }

  setActiveTab(tab: PermissionsTab): void {
    this.activeTab = tab;
  }

  loadCatalog(): void {
    this.errorMessage = '';
    this.isLoadingCatalog = true;

    forkJoin({
      modules: this.permissionsService.getModules('all'),
      actions: this.permissionsService.getActions({ active: 'all' }),
      routes: this.permissionsService.getRoutes({ active: 'all' }),
    })
      .pipe(finalize(() => {
        this.isLoadingCatalog = false;
      }))
      .subscribe({
        next: (response) => {
          this.modules = response.modules.modules || [];
          this.actions = response.actions.actions || [];
          this.routes = response.routes.routes || [];
        },
        error: () => {
          this.errorMessage = 'No se pudo cargar el catálogo de permisos.';
        },
      });
  }

  loadEffectivePermissions(): void {
    const userId = Number(this.userIdInput);

    if (!Number.isInteger(userId) || userId <= 0) {
      this.errorMessage = 'Captura un ID de usuario válido.';
      return;
    }

    this.errorMessage = '';
    this.isLoadingEffective = true;

    this.permissionsService
      .getEffectivePermissions(userId, 'all')
      .pipe(finalize(() => {
        this.isLoadingEffective = false;
      }))
      .subscribe({
        next: (response) => {
          this.effectivePermissions = response;
          this.activeTab = 'effective';
        },
        error: () => {
          this.errorMessage = 'No se pudieron consultar los permisos efectivos del usuario.';
        },
      });
  }

  get summaryCards(): SummaryCard[] {
    const activeRoutes = this.routes.filter((route) => route.is_active).length;
    const inactiveRoutes = this.routes.length - activeRoutes;

    return [
      {
        label: 'Módulos',
        value: String(this.modules.length),
        tone: 'neutral',
      },
      {
        label: 'Acciones',
        value: String(this.actions.length),
        tone: 'neutral',
      },
      {
        label: 'Rutas mapeadas',
        value: String(this.routes.length),
        tone: 'success',
      },
      {
        label: 'Rutas inactivas',
        value: String(inactiveRoutes),
        tone: inactiveRoutes > 0 ? 'warning' : 'neutral',
      },
    ];
  }

  get filteredActions(): PermissionAction[] {
    return this.actions.filter((action) => {
      if (this.selectedModuleKey && action.module_key !== this.selectedModuleKey) {
        return false;
      }

      if (this.selectedRiskLevel && action.risk_level !== this.selectedRiskLevel) {
        return false;
      }

      return true;
    });
  }

  get filteredRoutes(): PermissionRouteMap[] {
    return this.routes.filter((route) => {
      if (!this.showInactiveRoutes && !route.is_active) {
        return false;
      }

      if (this.selectedModuleKey && route.module_key !== this.selectedModuleKey) {
        return false;
      }

      if (this.selectedReviewStatus && route.review_status !== this.selectedReviewStatus) {
        return false;
      }

      return true;
    });
  }

  get allowedEffectiveActions(): EffectivePermissionAction[] {
    return this.effectivePermissions?.actions?.filter((action) => action.allowed) || [];
  }

  get deniedEffectiveActions(): EffectivePermissionAction[] {
    return this.effectivePermissions?.actions?.filter((action) => !action.allowed) || [];
  }

  get riskLevels(): string[] {
    return Array.from(
      new Set(this.actions.map((action) => action.risk_level).filter(Boolean)),
    ).sort();
  }

  get reviewStatuses(): string[] {
    return Array.from(
      new Set(this.routes.map((route) => route.review_status).filter(Boolean)),
    ).sort();
  }

  getModuleName(moduleKey?: string | null): string {
    const module = this.modules.find((item) => item.key === moduleKey);
    return module?.name || moduleKey || 'Sin módulo';
  }

  getSummaryCardClass(card: SummaryCard): string {
    return `permissions-summary-card permissions-summary-card--${card.tone}`;
  }

  getTabClass(tab: PermissionsTab): string {
    return this.activeTab === tab
      ? 'permissions-tab permissions-tab--active'
      : 'permissions-tab';
  }

  getRiskBadgeClass(riskLevel: string): string {
    return `permissions-badge permissions-badge--risk-${riskLevel || 'unknown'}`;
  }

  getRouteStatusClass(route: PermissionRouteMap): string {
    return route.is_active
      ? 'permissions-badge permissions-badge--success'
      : 'permissions-badge permissions-badge--warning';
  }

  getDecisionBadgeClass(action: EffectivePermissionAction): string {
    return action.allowed
      ? 'permissions-badge permissions-badge--success'
      : 'permissions-badge permissions-badge--danger';
  }

  trackByModuleKey(_: number, module: PermissionModule): string {
    return module.key;
  }

  trackByActionFullKey(_: number, action: PermissionAction): string {
    return action.full_key;
  }

  trackByRouteId(_: number, route: PermissionRouteMap): number {
    return route.id;
  }

  trackByEffectiveAction(_: number, action: EffectivePermissionAction): string {
    return action.full_key;
  }
}
