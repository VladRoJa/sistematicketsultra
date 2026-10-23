import { CommonModule } from '@angular/common';
import { Component, OnInit } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { finalize, forkJoin } from 'rxjs';
import {
  PermissionAction, PermissionModule, PermissionUserOption,
  PermissionsObservabilityService,
} from './permissions-observability.service';
import {
  AuditPerspective, PermissionVisualAuditService, VisualAuditFilters,
  VisualAuditResponse, VisualAuditRow,
} from './permission-visual-audit.service';

type DecisionFilter = 'todos' | 'permitido' | 'denegado' | 'no_concluyente' | 'diferencia';

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
  branchId = '';
  documentId = '';
  userSearch = '';
  search = '';
  decisionFilter: DecisionFilter = 'todos';

  readonly pageSize = 25;
  offset = 0;
  result: VisualAuditResponse | null = null;
  loading = false;
  loadingCatalog = false;
  loadingUsers = false;
  error = '';
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

  setView(view: AuditPerspective): void {
    this.view = view;
    this.offset = 0;
    this.result = null;
    this.error = '';
    this.decisionFilter = 'todos';
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

  private positiveInteger(input: string): number | undefined {
    if (!input.trim()) { return undefined; }
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
    };
    const version = ++this.requestVersion;
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

  get rows(): VisualAuditRow[] {
    const rows = this.result?.rows || [];
    if (this.decisionFilter === 'todos') { return rows; }
    return rows.filter(row =>
      this.decisionFilter === 'diferencia'
        ? row.comparison === 'diferencia'
        : row.status === this.decisionFilter
    );
  }

  startsModule(index: number): boolean {
    return this.view === 'user' &&
      (index === 0 || this.rows[index].module_key !== this.rows[index - 1].module_key);
  }

  navigateTo(view: AuditPerspective, row: VisualAuditRow): void {
    this.selectedUserId = row.user_id;
    this.userSearch = row.username;
    this.searchUsers();
    this.moduleKey = row.module_key || '';
    this.actionKey = row.action_key || '';
    this.view = view;
    this.decisionFilter = 'todos';
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

  exportCurrentPageCsv(): void {
    if (!this.rows.length) { return; }
    const fields: (keyof VisualAuditRow)[] = [
      'user_id', 'username', 'role', 'module_key', 'action_key',
      'legacy_allowed', 'legacy_source', 'legacy_reason', 'catalog_allowed',
      'catalog_source', 'catalog_reason', 'comparison', 'scope',
    ];
    const value = (raw: unknown): string =>
      '"' + String(raw === null || raw === undefined ? '?' : raw)
        .replace(/"/g, '""').replace(/^[=+@-]/, "'$&") + '"';
    const csv = '\uFEFF' + fields.join(',') + '\r\n' +
      this.rows.map(row => fields.map(field => value(row[field])).join(',')).join('\r\n');
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
