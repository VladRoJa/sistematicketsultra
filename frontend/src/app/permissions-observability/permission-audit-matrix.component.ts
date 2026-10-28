import { CommonModule } from '@angular/common';
import { Component, OnInit } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { finalize, forkJoin } from 'rxjs';
import {
  PermissionAction, PermissionModule, PermissionUserOption,
  PermissionsObservabilityService,
} from './permissions-observability.service';
import {
  permissionActionExplanation, permissionActionLabel, permissionActionPurpose,
} from './permission-action-labels';
import {
  AuditDecisionFilter, AuditGroupBy, AuditPerspective, AuditSortBy,
  PermissionVisualAuditService, VisualAuditFilters, VisualAuditResponse,
  VisualAuditRow,
} from './permission-visual-audit.service';

@Component({
  selector: 'app-permission-audit-matrix',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './permission-audit-matrix.component.html',
  styleUrls: ['./permission-audit-matrix.component.css'],
})
export class PermissionAuditMatrixComponent implements OnInit {
  view: AuditPerspective = 'user';
  modules: PermissionModule[] = [];
  actions: PermissionAction[] = [];
  users: PermissionUserOption[] = [];

  selectedUserId: number | null = null;
  moduleKey = '';
  actionKey = '';
  role = '';
  branchId: string | number = '';
  documentId: string | number = '';
  userSearch = '';
  search = '';
  decisionFilter: AuditDecisionFilter = 'todos';
  groupBy: AuditGroupBy = 'module';
  sortBy: AuditSortBy = 'action';
  sortDir: 'asc' | 'desc' = 'asc';

  readonly groupOptions: { value: AuditGroupBy; label: string }[] = [
    { value: 'none', label: 'Sin agrupar' },
    { value: 'legacy_permitido', label: 'Legacy · permitidos primero' },
    { value: 'legacy_denegado', label: 'Legacy · denegados primero' },
    { value: 'legacy_no_concluyente', label: 'Legacy · sin comprobar primero' },
    { value: 'catalog_permitido', label: 'Catálogo · permitidos primero' },
    { value: 'catalog_denegado', label: 'Catálogo · denegados primero' },
    { value: 'comparison_diferencia', label: 'Comparación · diferencias primero' },
    { value: 'comparison_coincide', label: 'Comparación · coincidencias primero' },
    { value: 'module', label: 'Por módulo' },
    { value: 'role', label: 'Por rol' },
  ];

  readonly pageSize = 25;
  offset = 0;
  result: VisualAuditResponse | null = null;
  loading = false;
  loadingCatalog = false;
  loadingUsers = false;
  error = '';
  saveError = '';
  savingTrackUserId: number | null = null;
  private requestVersion = 0;

  constructor(
    private readonly audit: PermissionVisualAuditService,
    private readonly catalog: PermissionsObservabilityService,
  ) {}

  ngOnInit(): void {
    this.loadingCatalog = true;
    forkJoin({
      modules: this.catalog.getModules('true'),
      actions: this.catalog.getActions({ active: 'true' }),
    }).pipe(finalize(() => { this.loadingCatalog = false; })).subscribe({
      next: ({ modules, actions }) => {
        this.modules = modules.modules || [];
        this.actions = actions.actions || [];
      },
      error: () => { this.error = 'No se pudo cargar el catálogo.'; },
    });
    this.searchUsers();
  }

  searchUsers(): void {
    this.loadingUsers = true;
    this.catalog.searchUsers(this.userSearch, 50)
      .pipe(finalize(() => { this.loadingUsers = false; }))
      .subscribe({
        next: response => {
          this.users = response.users || [];
          // Una selección previa permanece aunque no esté entre los primeros resultados.
        },
        error: () => { this.error = 'No se pudo consultar usuarios.'; },
      });
  }

  get moduleActions(): PermissionAction[] {
    return this.actions.filter(action => !this.moduleKey || action.module_key === this.moduleKey);
  }

  actionLabel(key: string | null | undefined, fallback?: string | null): string {
    return permissionActionLabel(key, fallback);
  }

  actionExplanation(key: string | null | undefined, fallback?: string | null): string {
    return permissionActionExplanation(key, fallback);
  }

  actionPurpose(key: string | null | undefined): string {
    return permissionActionPurpose(key);
  }

  setView(view: AuditPerspective): void {
    this.view = view;
    this.offset = 0;
    this.result = null;
    this.error = '';
    this.decisionFilter = 'todos';
    this.groupBy = view === 'user' ? 'module' : 'none';
    this.sortBy = view === 'user' ? 'action' : 'user';
    this.sortDir = 'asc';
    this.requestVersion++;
    this.load();
  }

  onModuleChanged(): void {
    if (this.actionKey && !this.moduleActions.some(action => action.full_key === this.actionKey)) {
      this.actionKey = '';
    }
    this.applyFilters();
  }

  onActionChanged(): void {
    const action = this.actions.find(item => item.full_key === this.actionKey);
    if (action?.module_key) {
      this.moduleKey = action.module_key;
    }
    if (this.actionKey !== 'internal_documents.view') {
      this.documentId = '';
    }
    this.applyFilters();
  }

  applyFilters(): void {
    this.offset = 0;
    this.load();
  }

  setSort(key: AuditSortBy): void {
    this.sortDir = this.sortBy === key && this.sortDir === 'asc' ? 'desc' : 'asc';
    this.sortBy = key;
    this.applyFilters();
  }

  sortArrow(key: AuditSortBy): string {
    return this.sortBy !== key ? '↕' : this.sortDir === 'asc' ? '▲' : '▼';
  }

  private positiveInteger(input: string | number | null | undefined): number | undefined {
    if (input === null || input === undefined || !String(input).trim()) { return undefined; }
    const value = Number(input);
    return Number.isSafeInteger(value) && value > 0 ? value : undefined;
  }

  load(): void {
    this.error = '';
    if ((this.branchId && !this.positiveInteger(this.branchId)) ||
        (this.documentId && !this.positiveInteger(this.documentId))) {
      this.error = 'Sucursal y documento deben ser IDs enteros positivos.';
      return;
    }
    if (this.view === 'user' && !this.selectedUserId ||
        this.view === 'module' && !this.moduleKey ||
        this.view === 'action' && !this.actionKey) {
      this.result = null;
      return;
    }
    const filters: VisualAuditFilters = {
      view: this.view, user_id: this.selectedUserId || undefined,
      module_key: this.moduleKey || undefined,
      action_key: this.actionKey || undefined,
      branch_id: this.positiveInteger(this.branchId),
      document_id: this.positiveInteger(this.documentId),
      role: this.view === 'user' ? undefined : this.role.trim() || undefined,
      q: this.view === 'user' ? undefined : this.search.trim() || undefined,
      limit: this.pageSize, offset: this.offset,
      sort_by: this.sortBy, sort_dir: this.sortDir,
      group_by: this.groupBy, decision: this.decisionFilter,
    };
    const version = ++this.requestVersion;
    this.result = null;
    this.loading = true;
    this.audit.getMatrix(filters)
      .pipe(finalize(() => { if (version === this.requestVersion) { this.loading = false; } }))
      .subscribe({
        next: response => {
          if (version !== this.requestVersion) { return; }
          this.result = response;
        },
        error: response => {
          if (version !== this.requestVersion) { return; }
          this.result = null;
          this.error = response?.error?.error || 'No se pudo consultar la matriz.';
        },
      });
  }

  canEditTrackRead(row: VisualAuditRow): boolean {
    // Solo la acción con autorización HTTP conectada y sin filtro de objeto.
    return row.action_key === 'track.read' &&
      row.module_key === 'track' && row.action_id !== null &&
      !row.context?.branch_id && !row.context?.document_id;
  }

  isSavingTrackRead(row: VisualAuditRow): boolean {
    return this.savingTrackUserId === row.user_id;
  }

  toggleTrackRead(row: VisualAuditRow, checked: boolean): void {
    if (!this.canEditTrackRead(row) || this.savingTrackUserId !== null) {
      return;
    }
    this.saveError = '';
    this.savingTrackUserId = row.user_id;
    this.catalog.setTrackReadAccess(row.user_id, checked)
      .pipe(finalize(() => { this.savingTrackUserId = null; }))
      .subscribe({
        next: () => { this.load(); },
        error: response => {
          this.saveError = response?.error?.detail ||
            'No se pudo guardar el permiso Track. No se aplicó el cambio.';
          this.load(); // relectura obligatoria: no conservar el estado del click
        },
      });
  }

  get rows(): VisualAuditRow[] {
    return this.result?.rows || [];
  }

  startsGroup(index: number): boolean {
    return this.groupBy !== 'none' &&
      (index === 0 || this.rows[index].group_key !== this.rows[index - 1].group_key);
  }

  groupCount(row: VisualAuditRow): number {
    return this.result?.group_counts[row.group_key] || 0;
  }

  navigateTo(view: AuditPerspective, row: VisualAuditRow): void {
    this.selectedUserId = row.user_id;
    this.userSearch = row.username;
    this.searchUsers();
    this.moduleKey = row.module_key || '';
    this.actionKey = row.action_key || '';
    this.view = view;
    this.decisionFilter = 'todos';
    this.groupBy = view === 'user' ? 'module' : 'none';
    this.sortBy = view === 'user' ? 'action' : 'user';
    this.sortDir = 'asc';
    this.offset = 0;
    this.result = null;
    this.load();
  }

  next(): void {
    if (this.result && this.offset + this.pageSize < this.result.summary.total) {
      this.offset += this.pageSize;
      this.load();
    }
  }

  previous(): void {
    this.offset = Math.max(0, this.offset - this.pageSize);
    this.load();
  }

  get lastRow(): number {
    return Math.min(this.offset + this.pageSize, this.result?.summary.total || 0);
  }

  get rowCount(): number {
    return this.result?.summary.total || 0;
  }

  getBooleanLabel(value: boolean | null): string {
    return value === null ? 'Sin comprobar' : value ? 'Permitido' : 'Denegado';
  }

  getScopeLabel(row: VisualAuditRow): string {
    if (row.scope === 'global') { return 'Guard de alcance global'; }
    if (row.scope === 'guard_rol_base') { return 'Solo condición inicial del rol (no valida sucursal ni registro)'; }
    if (row.scope === 'sucursal') {
      return 'Guard de movimiento para sucursal #' + row.context.branch_id;
    }
    if (row.scope === 'documento') { return 'Depende de la visibilidad del documento'; }
    return 'Se requiere contexto adicional';
  }

  getAuditReason(row: VisualAuditRow, origin: 'legacy' | 'catalog'): string {
    const allowed = origin === 'legacy' ? row.legacy_allowed : row.catalog_allowed;
    const reason = origin === 'legacy' ? row.legacy_reason : row.catalog_reason;
    const source = origin === 'legacy' ? row.legacy_source : row.catalog_source;

    if (origin === 'catalog' && source === 'grant_diagnostico_no_enforcement') {
      return 'Existe un grant en el catálogo diagnóstico. No modifica el acceso real.';
    }
    if (row.action_key === 'track.read' &&
        (origin === 'legacy' || reason === 'track_read_role_matches_guard_v2')) {
      const label = allowed === true ? 'incluido entre los roles autorizados'
        : allowed === false ? 'fuera de los roles autorizados'
        : 'sin verificar';
      return (origin === 'legacy' ? 'Guard real de Track: ' : 'Catálogo diagnóstico de Track: ') +
        'rol ' + label + ' para consultar indicadores.';
    }

    const explanations: Record<string, string> = {
      'guard_de_rol_track': 'La consulta se determina por el rol del usuario.',
      'pm_gate_rol_o_lectura_individual': 'El rol o permiso individual cumple el control inicial de PM; faltan los controles del registro y sucursal.',
      'pm_sucursal_requiere_validacion_de_recurso': 'PM necesita validar el alcance por sucursal y el registro específico.',
      'inventario_guard_global_rol': 'El rol cumple o incumple el control de administración del inventario maestro.',
      'inventario_movimiento_requiere_sucursal': 'Para evaluar movimientos es obligatorio seleccionar una sucursal.',
      'inventario_movimiento_guard_sucursal': 'Se comprobó el control de rol y sucursal de un movimiento; no la validez de la operación.',
      'tickets_borrado_masivo_guard_doble': 'La operación masiva exige administrador y ALLOW_TICKET_DELETE_ALL=true; no se ejecutó ningún borrado.',
      'guard_admin_track': 'La ejecución de procesos de Track exige un rol administrador.',
      'manager_legacy_verificado': 'El permiso de administración documental se comprobó con la regla vigente.',
      'documento_y_visibilidad_evaluados': 'Se evaluó el acceso al documento específico.',
      'allowlist_y_flag': 'La regla valida el registro y las facultades del operador Warehouse.',
      'operador_activo_y_flag': 'La regla requiere un operador activo y una facultad habilitada.',
      'requiere_guard_especifico_o_contexto_de_objeto': 'No se puede comprobar sin el guard o el registro correspondiente.',
      'branch_guard_no_evaluable_sin_recurso': 'La sucursal indicada no basta para validar acceso al registro.',
      'modulo_sin_accion_base': 'No hay una acción base que permita comprobar esta entrada.',
      'grant_con_alcance_o_vigencia_no_resuelta': 'El alcance o vigencia del grant no se puede resolver aquí.',
      'catalogo_no_modela_visibilidad_de_este_documento': 'El catálogo no determina permisos de lectura para este documento específico.',
      'accion_sin_proyeccion_mapeada_o_inactiva': 'El catálogo todavía no tiene una proyección vigente para esta acción.',
    };
    if (explanations[reason]) { return explanations[reason]; }
    if (origin === 'legacy') {
      return allowed === null ? 'El guard real todavía no puede comprobarse desde esta consulta.'
        : allowed ? 'La regla operativa permite esta acción.' : 'La regla operativa deniega esta acción.';
    }
    return allowed === null ? 'El catálogo no puede estimar esta decisión.'
      : allowed ? 'El catálogo estima que la acción está permitida.'
      : 'El catálogo estima que la acción está denegada.';
  }


  exportCurrentPageCsv(): void {
    if (!this.rows.length) { return; }
    const fields: (keyof VisualAuditRow)[] = [
      'user_id', 'username', 'role', 'module_key', 'action_key',
      'legacy_allowed', 'legacy_source', 'legacy_reason', 'catalog_allowed',
      'catalog_source', 'catalog_reason', 'comparison', 'scope',
    ];
    const headers = [
      ...fields, 'action_label', 'action_purpose', 'action_explanation',
    ];
    const value = (raw: unknown): string =>
      '"' + String(raw === null || raw === undefined ? '?' : raw)
        .replace(/"/g, '""').replace(/^[=+@-]/, "'$&") + '"';
    const csv = '\uFEFF' + headers.join(',') + '\r\n' +
      this.rows.map(row => [
        ...fields.map(field => row[field]),
        this.actionLabel(row.action_key, row.action_name),
        this.actionPurpose(row.action_key),
        this.actionExplanation(row.action_key),
      ].map(value).join(',')).join('\r\n');
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = 'suite_ultra_auditoria_' + this.view + '_pagina.csv';
    anchor.click();
    URL.revokeObjectURL(url);
  }

  trackRow(index: number, row: VisualAuditRow): string {
    return row.user_id + ':' + row.action_id + ':' + index;
  }
}
