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
  PermissionGrant,
  PermissionGrantAuditLog,
  PermissionModule,
  PermissionRouteMap,
  PermissionUserOption,
  PermissionsObservabilityService,
} from './permissions-observability.service';

type PermissionsTab = 'modules' | 'actions' | 'routes' | 'effective' | 'grants';
type EffectiveDecisionFilter = 'all' | 'allowed' | 'denied';
type RouteAuditFilter = 'all' | 'active' | 'inactive' | 'without_action';

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
  grants: PermissionGrant[] = [];
  selectedGrantForAudit: PermissionGrant | null = null;
  selectedGrantAuditLogs: PermissionGrantAuditLog[] = [];

  selectedModuleKey = '';
  selectedRiskLevel = '';
  selectedReviewStatus = '';
  showInactiveRoutes = true;
  routeSearchTerm = '';
  routeAuditFilter: RouteAuditFilter = 'all';
  selectedRouteRiskLevel = '';
  selectedRouteGuard = '';
  selectedRouteScope = '';
  effectiveSearchTerm = '';
  effectiveDecisionFilter: EffectiveDecisionFilter = 'all';

  grantSearchTerm = '';
  grantActiveFilter: 'true' | 'false' | 'all' = 'all';
  grantPrincipalTypeFilter = '';
  grantPrincipalUserIdFilter = '';
  grantPrincipalRoleKeyFilter = '';
  grantModuleKeyFilter = '';
  grantActionFullKeyFilter = '';
  grantEffectFilter = '';
  grantScopeTypeFilter = '';

  userIdInput = '';
  userSearchTerm = '';
  userOptions: PermissionUserOption[] = [];
  selectedUserOptionId: number | null = null;
  effectivePermissions: EffectivePermissionResponse | null = null;

  isLoadingCatalog = false;
  isLoadingUsers = false;
  isLoadingEffective = false;
  isLoadingGrants = false;
  isLoadingGrantAudit = false;
  errorMessage = '';

  constructor(
    private readonly permissionsService: PermissionsObservabilityService,
    private readonly session: SessionService,
  ) {}

  ngOnInit(): void {
    const currentUser = this.session.getUser();
    this.userIdInput = currentUser?.id ? String(currentUser.id) : '';

    this.loadCatalog();
    this.loadGrants();
    this.loadUserOptions();

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


  loadUserOptions(): void {
    this.errorMessage = '';
    this.isLoadingUsers = true;

    this.permissionsService
      .searchUsers(this.userSearchTerm, 50)
      .pipe(finalize(() => {
        this.isLoadingUsers = false;
      }))
      .subscribe({
        next: (response) => {
          this.userOptions = response.users || [];

          const currentUserId = Number(this.userIdInput);
          if (currentUserId > 0) {
            const exists = this.userOptions.some((user) => user.id === currentUserId);
            this.selectedUserOptionId = exists ? currentUserId : null;
          }
        },
        error: () => {
          this.errorMessage = 'No se pudo buscar usuarios.';
        },
      });
  }

  selectUserForEffectivePermissions(user: PermissionUserOption): void {
    this.selectedUserOptionId = user.id;
    this.userIdInput = String(user.id);
    this.loadEffectivePermissions();
  }

  onSelectedUserOptionChanged(): void {
    if (!this.selectedUserOptionId) {
      return;
    }

    this.userIdInput = String(this.selectedUserOptionId);
    this.loadEffectivePermissions();
  }

  loadGrants(): void {
    this.errorMessage = '';
    this.isLoadingGrants = true;

    const principalUserId = Number(this.grantPrincipalUserIdFilter);

    this.permissionsService
      .getGrants({
        active: this.grantActiveFilter,
        principal_type: this.grantPrincipalTypeFilter,
        principal_user_id: Number.isInteger(principalUserId) && principalUserId > 0
          ? principalUserId
          : null,
        principal_role_key: this.grantPrincipalRoleKeyFilter.trim(),
        module_key: this.grantModuleKeyFilter.trim(),
        action_full_key: this.grantActionFullKeyFilter.trim(),
        effect: this.grantEffectFilter,
        scope_type: this.grantScopeTypeFilter,
        limit: 200,
        offset: 0,
      })
      .pipe(finalize(() => {
        this.isLoadingGrants = false;
      }))
      .subscribe({
        next: (response) => {
          this.grants = response.grants || [];

          if (
            this.selectedGrantForAudit &&
            !this.grants.some((grant) => grant.id === this.selectedGrantForAudit?.id)
          ) {
            this.clearGrantAudit();
          }
        },
        error: () => {
          this.errorMessage = 'No se pudieron consultar los grants.';
        },
      });
  }

  loadGrantAudit(grant: PermissionGrant): void {
    this.errorMessage = '';
    this.selectedGrantForAudit = grant;
    this.selectedGrantAuditLogs = [];
    this.isLoadingGrantAudit = true;

    this.permissionsService
      .getGrantAudit(grant.id, {
        limit: 100,
        offset: 0,
      })
      .pipe(finalize(() => {
        this.isLoadingGrantAudit = false;
      }))
      .subscribe({
        next: (response) => {
          this.selectedGrantForAudit = response.grant;
          this.selectedGrantAuditLogs = response.audit_logs || [];
        },
        error: () => {
          this.errorMessage = 'No se pudo consultar la auditoría del grant.';
        },
      });
  }

  clearGrantAudit(): void {
    this.selectedGrantForAudit = null;
    this.selectedGrantAuditLogs = [];
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

  get filteredGrants(): PermissionGrant[] {
    const searchTerm = this.grantSearchTerm.trim().toLowerCase();

    if (!searchTerm) {
      return this.grants;
    }

    return this.grants.filter((grant) => {
      const searchable = [
        grant.id,
        grant.principal_type,
        grant.principal_user?.username,
        grant.principal_user?.email,
        grant.principal_role_key,
        grant.module_key,
        grant.module_name,
        grant.action_full_key,
        grant.action_name,
        grant.action_risk_level,
        grant.effect,
        grant.scope_type,
        grant.scope_branch_id,
        grant.scope_department_id,
        grant.reason,
        grant.created_by_user?.username,
        grant.updated_by_user?.username,
      ]
        .filter((value) => value !== null && value !== undefined)
        .join(' ')
        .toLowerCase();

      return searchable.includes(searchTerm);
    });
  }

  get activeGrantsCount(): number {
    return this.grants.filter((grant) => grant.is_active).length;
  }

  get inactiveGrantsCount(): number {
    return this.grants.filter((grant) => !grant.is_active).length;
  }

  get allowGrantsCount(): number {
    return this.grants.filter((grant) => grant.effect === 'allow').length;
  }

  get denyGrantsCount(): number {
    return this.grants.filter((grant) => grant.effect === 'deny').length;
  }

  get grantPrincipalTypes(): string[] {
    return ['user', 'role'];
  }

  get grantEffects(): string[] {
    return ['allow', 'deny'];
  }

  get grantScopeTypes(): string[] {
    return ['global', 'branch', 'branch_list', 'department', 'module', 'custom'];
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
    const searchTerm = this.routeSearchTerm.trim().toLowerCase();

    return this.routes.filter((route) => {
      if (!this.showInactiveRoutes && !route.is_active) {
        return false;
      }

      if (this.routeAuditFilter === 'active' && !route.is_active) {
        return false;
      }

      if (this.routeAuditFilter === 'inactive' && route.is_active) {
        return false;
      }

      if (this.routeAuditFilter === 'without_action' && route.action_id !== null) {
        return false;
      }

      if (this.selectedModuleKey && route.module_key !== this.selectedModuleKey) {
        return false;
      }

      if (this.selectedReviewStatus && route.review_status !== this.selectedReviewStatus) {
        return false;
      }

      if (this.selectedRouteGuard && route.current_guard !== this.selectedRouteGuard) {
        return false;
      }

      if (this.selectedRouteScope && route.current_scope !== this.selectedRouteScope) {
        return false;
      }

      if (this.selectedRouteRiskLevel) {
        const riskLevel = this.getRouteRiskLevel(route);
        if (riskLevel !== this.selectedRouteRiskLevel) {
          return false;
        }
      }

      if (!searchTerm) {
        return true;
      }

      const searchable = [
        route.method,
        route.route,
        route.endpoint_function,
        route.source_file,
        route.module_key,
        route.action_full_key,
        route.current_guard,
        route.current_scope,
        route.review_status,
        route.notes,
        this.getRouteRiskLevel(route),
      ]
        .filter(Boolean)
        .join(' ')
        .toLowerCase();

      return searchable.includes(searchTerm);
    });
  }

  get filteredEffectiveActions(): EffectivePermissionAction[] {
    const actions = this.effectivePermissions?.actions || [];
    const searchTerm = this.effectiveSearchTerm.trim().toLowerCase();

    return actions.filter((action) => {
      if (this.selectedModuleKey && action.module_key !== this.selectedModuleKey) {
        return false;
      }

      if (this.effectiveDecisionFilter === 'allowed' && !action.allowed) {
        return false;
      }

      if (this.effectiveDecisionFilter === 'denied' && action.allowed) {
        return false;
      }

      if (!searchTerm) {
        return true;
      }

      const searchable = [
        action.full_key,
        action.name,
        action.reason,
        action.source,
        action.scope_type,
        action.risk_level,
      ]
        .filter(Boolean)
        .join(' ')
        .toLowerCase();

      return searchable.includes(searchTerm);
    });
  }

  get allowedEffectiveActions(): EffectivePermissionAction[] {
    return this.filteredEffectiveActions.filter((action) => action.allowed);
  }

  get deniedEffectiveActions(): EffectivePermissionAction[] {
    return this.filteredEffectiveActions.filter((action) => !action.allowed);
  }

  get filteredEffectiveAllowedCount(): number {
    return this.allowedEffectiveActions.length;
  }

  get filteredEffectiveDeniedCount(): number {
    return this.deniedEffectiveActions.length;
  }

  shouldShowAllowedEffectiveSection(): boolean {
    return this.effectiveDecisionFilter !== 'denied';
  }

  shouldShowDeniedEffectiveSection(): boolean {
    return this.effectiveDecisionFilter !== 'allowed';
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

  get routeGuards(): string[] {
    return Array.from(
      new Set(
        this.routes
          .map((route) => route.current_guard)
          .filter((value): value is string => Boolean(value)),
      ),
    ).sort();
  }

  get routeScopes(): string[] {
    return Array.from(
      new Set(
        this.routes
          .map((route) => route.current_scope)
          .filter((value): value is string => Boolean(value)),
      ),
    ).sort();
  }

  get routeRiskLevels(): string[] {
    return Array.from(
      new Set(
        this.routes
          .map((route) => this.getRouteRiskLevel(route))
          .filter((value): value is string => Boolean(value)),
      ),
    ).sort();
  }

  get activeRoutesCount(): number {
    return this.routes.filter((route) => route.is_active).length;
  }

  get inactiveRoutesCount(): number {
    return this.routes.filter((route) => !route.is_active).length;
  }

  get routesWithoutActionCount(): number {
    return this.routes.filter((route) => route.action_id === null).length;
  }

  get criticalRoutesCount(): number {
    return this.routes.filter((route) => this.getRouteRiskLevel(route) === 'critical').length;
  }

  get highRoutesCount(): number {
    return this.routes.filter((route) => this.getRouteRiskLevel(route) === 'high').length;
  }

  get filteredRoutesCount(): number {
    return this.filteredRoutes.length;
  }

  getRouteRiskLevel(route: PermissionRouteMap): string {
    if (!route.action_full_key) {
      return '';
    }

    const action = this.actions.find((item) => item.full_key === route.action_full_key);
    return action?.risk_level || '';
  }

  getRouteAuditButtonClass(filter: RouteAuditFilter): string {
    return this.routeAuditFilter === filter
      ? 'permissions-audit-button permissions-audit-button--active'
      : 'permissions-audit-button';
  }

  setRouteAuditFilter(filter: RouteAuditFilter): void {
    this.routeAuditFilter = filter;
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
    if (route.action_id === null) {
      return 'permissions-badge permissions-badge--danger';
    }

    return route.is_active
      ? 'permissions-badge permissions-badge--success'
      : 'permissions-badge permissions-badge--warning';
  }

  getGrantEffectBadgeClass(grant: PermissionGrant): string {
    return grant.effect === 'deny'
      ? 'permissions-badge permissions-badge--danger'
      : 'permissions-badge permissions-badge--success';
  }

  getGrantStatusBadgeClass(grant: PermissionGrant): string {
    return grant.is_active
      ? 'permissions-badge permissions-badge--success'
      : 'permissions-badge permissions-badge--warning';
  }

  getGrantPrincipalLabel(grant: PermissionGrant): string {
    if (grant.principal_type === 'user') {
      return grant.principal_user
        ? `${grant.principal_user.username} #${grant.principal_user.id}`
        : `Usuario #${grant.principal_user_id || 'sin id'}`;
    }

    return grant.principal_role_key || 'Rol sin clave';
  }
  getDecisionBadgeClass(action: EffectivePermissionAction): string {
    return action.allowed
      ? 'permissions-badge permissions-badge--success'
      : 'permissions-badge permissions-badge--danger';
  }


  exportFilteredActionsCsv(): void {
    const rows = this.filteredActions.map((action) => ({
      module_key: action.module_key || '',
      module_name: this.getModuleName(action.module_key),
      full_key: action.full_key,
      key: action.key,
      name: action.name,
      description: action.description || '',
      risk_level: action.risk_level,
      is_active: action.is_active ? 'true' : 'false',
    }));

    this.downloadCsv(
      `suite_permissions_actions_${this.buildExportTimestamp()}.csv`,
      rows,
    );
  }

  exportFilteredRoutesCsv(): void {
    const rows = this.filteredRoutes.map((route) => ({
      method: route.method,
      route: route.route,
      endpoint_function: route.endpoint_function,
      source_file: route.source_file,
      module_key: route.module_key || '',
      module_name: this.getModuleName(route.module_key),
      action_full_key: route.action_full_key || '',
      risk_level: this.getRouteRiskLevel(route) || '',
      current_guard: route.current_guard || '',
      current_scope: route.current_scope || '',
      review_status: route.review_status,
      is_active: route.is_active ? 'true' : 'false',
      notes: route.notes || '',
    }));

    this.downloadCsv(
      `suite_permissions_routes_${this.buildExportTimestamp()}.csv`,
      rows,
    );
  }

  exportFilteredEffectivePermissionsCsv(): void {
    if (!this.effectivePermissions) {
      this.errorMessage = 'Consulta primero un usuario para exportar permisos efectivos.';
      return;
    }

    const rows = this.filteredEffectiveActions.map((action) => ({
      user_id: this.effectivePermissions?.user?.id || '',
      username: this.effectivePermissions?.user?.username || '',
      user_role: this.effectivePermissions?.user?.role || '',
      module_key: action.module_key || '',
      module_name: this.getModuleName(action.module_key),
      full_key: action.full_key,
      name: action.name,
      risk_level: action.risk_level,
      allowed: action.allowed ? 'true' : 'false',
      source: action.source,
      reason: action.reason,
      scope_type: action.scope_type,
      scope_values: JSON.stringify(action.scope_values || []),
    }));

    const username = this.sanitizeFilenamePart(
      this.effectivePermissions.user.username || 'usuario',
    );

    this.downloadCsv(
      `suite_permissions_effective_${username}_${this.buildExportTimestamp()}.csv`,
      rows,
    );
  }

  private downloadCsv(filename: string, rows: Array<Record<string, unknown>>): void {
    if (!rows.length) {
      this.errorMessage = 'No hay registros para exportar con los filtros actuales.';
      return;
    }

    this.errorMessage = '';

    const headers = Object.keys(rows[0]);
    const csvLines = [
      headers.map((header) => this.escapeCsvValue(header)).join(','),
      ...rows.map((row) =>
        headers
          .map((header) => this.escapeCsvValue(row[header]))
          .join(','),
      ),
    ];

    const csvContent = `\ufeff${csvLines.join('\r\n')}`;
    const blob = new Blob([csvContent], {
      type: 'text/csv;charset=utf-8;',
    });

    const url = window.URL.createObjectURL(blob);
    const link = document.createElement('a');

    link.href = url;
    link.download = filename;
    link.click();

    window.URL.revokeObjectURL(url);
  }

  private escapeCsvValue(value: unknown): string {
    if (value === null || value === undefined) {
      return '""';
    }

    const normalized = String(value).replace(/"/g, '""');
    return `"${normalized}"`;
  }

  private buildExportTimestamp(): string {
    const now = new Date();
    const pad = (value: number) => String(value).padStart(2, '0');

    return [
      now.getFullYear(),
      pad(now.getMonth() + 1),
      pad(now.getDate()),
      `${pad(now.getHours())}${pad(now.getMinutes())}${pad(now.getSeconds())}`,
    ].join('_');
  }

  private sanitizeFilenamePart(value: string): string {
    return value
      .trim()
      .toLowerCase()
      .replace(/[^a-z0-9_-]+/gi, '_')
      .replace(/_+/g, '_')
      .replace(/^_|_$/g, '') || 'usuario';
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

  trackByUserId(_: number, user: PermissionUserOption): number {
    return user.id;
  }
}




