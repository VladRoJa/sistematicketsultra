import { CommonModule } from '@angular/common';
import { Component, OnDestroy, OnInit } from '@angular/core';
import { FormBuilder, ReactiveFormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatPaginatorModule, PageEvent } from '@angular/material/paginator';
import { MatSelectModule } from '@angular/material/select';
import { MatTableModule } from '@angular/material/table';
import { Router } from '@angular/router';
import { Subject, Subscription, forkJoin, of } from 'rxjs';
import { catchError, debounceTime, finalize, startWith, switchMap } from 'rxjs/operators';
import {
  RoutineControlBranchCatalog,
  RoutineControlCatalogs,
  RoutineControlFilters,
  RoutineControlMember,
  RoutineControlMembersResponse,
  RoutineControlSummary,
  RoutineControlSummaryBranch,
  RoutineControlVisibleStatus,
} from '../models/routine-control.models';
import { RoutineControlService } from '../services/routine-control.service';

@Component({
  selector: 'app-routine-control-dashboard',
  standalone: true,
  imports: [
    CommonModule, ReactiveFormsModule, MatButtonModule, MatCardModule, MatFormFieldModule,
    MatIconModule, MatInputModule, MatPaginatorModule, MatSelectModule, MatTableModule,
  ],
  templateUrl: './routine-control-dashboard.component.html',
  styleUrls: ['./routine-control-dashboard.component.css'],
})
export class RoutineControlDashboardComponent implements OnInit, OnDestroy {
  readonly displayedColumns = [
    'member', 'external_member_id', 'branch', 'sale_date', 'status', 'first_routine_at',
    'latest_routine_at', 'instructor', 'assignment_type', 'incidents', 'detail',
  ];
  readonly form = this.fb.group({
    region_key: [''], branch_id: [null as number | null], sale_date_from: [''], sale_date_to: [''],
    current_status: [''], assignment_type: [''], instructor: [''], search: [''],
  });
  catalogs: RoutineControlCatalogs | null = null;
  summary: RoutineControlSummary | null = null;
  members: RoutineControlMember[] = [];
  total = 0;
  page = 1;
  pageSize = 25;
  loading = false;
  exporting = false;
  errorMessage = '';
  branchSort: keyof RoutineControlSummaryBranch = 'total_members';
  branchSortDirection: 'asc' | 'desc' = 'desc';
  private readonly reload$ = new Subject<void>();
  private readonly subscriptions = new Subscription();

  constructor(
    private readonly fb: FormBuilder,
    private readonly service: RoutineControlService,
    private readonly router: Router,
  ) {}

  ngOnInit(): void {
    this.loading = true;
    this.subscriptions.add(this.service.getCatalogs().subscribe({
      next: (catalogs) => {
        this.catalogs = catalogs;
        if (catalogs.scope.fixed_branch_id !== null) {
          this.form.controls.branch_id.setValue(catalogs.scope.fixed_branch_id, { emitEvent: false });
        }
        this.bindReloads();
      },
      error: () => {
        this.loading = false;
        this.errorMessage = 'No fue posible cargar el alcance y los catálogos.';
      },
    }));
  }

  ngOnDestroy(): void {
    this.subscriptions.unsubscribe();
  }

  get scopeLabel(): string {
    const type = this.catalogs?.scope.scope_type;
    return type === 'BRANCH' ? 'Mi sucursal' : type === 'REGIONAL' ? 'Mi región' : 'Vista nacional';
  }

  get canSelectRegion(): boolean {
    return this.catalogs?.scope.scope_type === 'GLOBAL';
  }

  get canSelectBranch(): boolean {
    return this.catalogs?.scope.scope_type !== 'BRANCH';
  }

  get availableBranches(): RoutineControlBranchCatalog[] {
    const regionKey = this.form.controls.region_key.value;
    if (!regionKey) return this.catalogs?.branches || [];
    return (this.catalogs?.branches || []).filter((branch) => branch.region_key === regionKey);
  }

  get sortedBranches(): RoutineControlSummaryBranch[] {
    const multiplier = this.branchSortDirection === 'asc' ? 1 : -1;
    return [...(this.summary?.branches || [])].sort((left, right) => {
      const leftValue = Number(left[this.branchSort] || 0);
      const rightValue = Number(right[this.branchSort] || 0);
      return (leftValue - rightValue) * multiplier;
    });
  }

  get maxBranchTotal(): number {
    return Math.max(1, ...(this.summary?.branches || []).map((branch) => branch.total_members));
  }

  statusOf(member: RoutineControlMember): RoutineControlVisibleStatus {
    return member.classification_status === 'INCIDENT' ? 'INCIDENT' : member.current_status || 'INCIDENT';
  }

  statusLabel(status: RoutineControlVisibleStatus): string {
    return ({
      CON_RUTINA: 'Con rutina', SIN_RUTINA: 'Sin rutina', NO_DESEA_RUTINA: 'No desea rutina', INCIDENT: 'Incidencia',
    })[status];
  }

  statusClass(status: RoutineControlVisibleStatus): string {
    return `status status--${status.toLowerCase()}`;
  }

  branchBarWidth(branch: RoutineControlSummaryBranch): number {
    return Math.round((branch.total_members / this.maxBranchTotal) * 100);
  }

  selectRegion(): void {
    const selected = this.form.controls.branch_id.value;
    if (selected !== null && !this.availableBranches.some((branch) => branch.id === selected)) {
      this.form.controls.branch_id.setValue(null);
    }
  }

  selectBranch(branchId: number | null): void {
    if (branchId === null || !this.canSelectBranch) return;
    this.form.controls.branch_id.setValue(branchId);
  }

  sortBranches(field: keyof RoutineControlSummaryBranch): void {
    if (this.branchSort === field) {
      this.branchSortDirection = this.branchSortDirection === 'asc' ? 'desc' : 'asc';
      return;
    }
    this.branchSort = field;
    this.branchSortDirection = 'desc';
  }

  clearFilters(): void {
    const fixedBranch = this.catalogs?.scope.fixed_branch_id ?? null;
    this.form.reset({
      region_key: '', branch_id: fixedBranch, sale_date_from: '', sale_date_to: '', current_status: '',
      assignment_type: '', instructor: '', search: '',
    });
  }

  pageChanged(event: PageEvent): void {
    this.page = event.pageIndex + 1;
    this.pageSize = event.pageSize;
    this.reload$.next();
  }

  openDetail(memberId: number): void {
    this.router.navigate(['/control-rutinas/socios', memberId]);
  }

  openRuns(): void {
    this.router.navigate(['/control-rutinas/corridas']);
  }

  exportMembers(): void {
    this.exporting = true;
    this.service.exportMembers(this.currentFilters()).pipe(
      finalize(() => this.exporting = false),
    ).subscribe({
      next: (response) => this.service.downloadExport(response),
      error: () => this.errorMessage = 'No fue posible exportar. Ajusta los filtros e intenta de nuevo.',
    });
  }

  private bindReloads(): void {
    this.subscriptions.add(this.form.valueChanges.pipe(debounceTime(350)).subscribe(() => {
      this.page = 1;
      this.reload$.next();
    }));
    this.subscriptions.add(this.reload$.pipe(
      startWith(undefined),
      switchMap(() => {
        this.loading = true;
        this.errorMessage = '';
        const filters = this.currentFilters();
        return forkJoin({
          summary: this.service.getSummary(filters),
          members: this.service.getMembers(filters),
        }).pipe(
          catchError(() => {
            this.errorMessage = 'No fue posible consultar Control de Rutinas.';
            return of({ summary: null, members: null });
          }),
          finalize(() => this.loading = false),
        );
      }),
    ).subscribe((result: { summary: RoutineControlSummary | null; members: RoutineControlMembersResponse | null }) => {
      if (!result.summary || !result.members) return;
      this.summary = result.summary;
      this.members = result.members.items;
      this.total = result.members.total;
    }));
  }

  private currentFilters(): RoutineControlFilters {
    const value = this.form.getRawValue();
    const visibleStatus = value.current_status || null;
    return {
      region_key: value.region_key || null,
      branch_id: value.branch_id,
      sale_date_from: value.sale_date_from || null,
      sale_date_to: value.sale_date_to || null,
      classification_status: visibleStatus === 'INCIDENT' ? 'INCIDENT' : null,
      current_status: visibleStatus && visibleStatus !== 'INCIDENT' ? visibleStatus as RoutineControlFilters['current_status'] : null,
      assignment_type: value.assignment_type as RoutineControlFilters['assignment_type'],
      instructor: value.instructor || null,
      search: value.search || null,
      page: this.page,
      page_size: this.pageSize,
      sort: 'sale_date',
      direction: 'desc',
    };
  }
}
