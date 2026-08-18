import { HttpErrorResponse } from '@angular/common/http';
import { CommonModule } from '@angular/common';
import {
  Component,
  DestroyRef,
  OnInit,
  inject,
} from '@angular/core';
import { FormControl, ReactiveFormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import {
  MAT_DIALOG_DATA,
  MatDialogModule,
  MatDialogRef,
} from '@angular/material/dialog';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import {
  MatPaginatorModule,
  PageEvent,
} from '@angular/material/paginator';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import {
  MatSnackBar,
  MatSnackBarModule,
} from '@angular/material/snack-bar';
import { MatTableModule } from '@angular/material/table';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { debounceTime, distinctUntilChanged } from 'rxjs';

import {
  MarketingFunnelDetailKind,
  MarketingInvestmentDetailResponse,
  MarketingInvestmentDetailRow,
  MarketingLeadDetailRow,
  MarketingLeadsDetailResponse,
  MarketingVisitorDetailRow,
  MarketingVisitorsDetailResponse,
} from './marketing.models';
import { MarketingExcelExportService } from './marketing-excel-export.service';
import { MarketingService } from './marketing.service';

export interface MarketingFunnelDetailDialogData {
  kind: MarketingFunnelDetailKind;
  month: string;
  branchId?: number;
  branchName?: string;
}

interface MarketingDetailSummaryCard {
  label: string;
  value: string;
}

@Component({
  selector: 'app-marketing-funnel-detail-dialog',
  standalone: true,
  imports: [
    CommonModule,
    MatButtonModule,
    MatDialogModule,
    MatFormFieldModule,
    MatIconModule,
    MatInputModule,
    MatPaginatorModule,
    MatProgressSpinnerModule,
    MatSnackBarModule,
    MatTableModule,
    ReactiveFormsModule,
  ],
  templateUrl: './marketing-funnel-detail-dialog.component.html',
  styleUrls: [
    './marketing-attribution-detail-dialog.component.css',
    './marketing-funnel-detail-dialog.component.css',
  ],
})
export class MarketingFunnelDetailDialogComponent
  implements OnInit
{
  private readonly destroyRef = inject(DestroyRef);
  private readonly marketingService = inject(MarketingService);
  private readonly excelExport = inject(MarketingExcelExportService);
  private readonly snackBar = inject(MatSnackBar);
  private readonly dialogRef = inject(
    MatDialogRef<MarketingFunnelDetailDialogComponent>,
  );

  readonly data = inject(
    MAT_DIALOG_DATA,
  ) as MarketingFunnelDetailDialogData;
  readonly searchControl = new FormControl('', { nonNullable: true });
  readonly pageSizeOptions = [50, 100, 250];

  investmentDetail: MarketingInvestmentDetailResponse | null = null;
  leadsDetail: MarketingLeadsDetailResponse | null = null;
  visitorsDetail: MarketingVisitorsDetailResponse | null = null;

  investmentRows: MarketingInvestmentDetailRow[] = [];
  leadRows: MarketingLeadDetailRow[] = [];
  visitorRows: MarketingVisitorDetailRow[] = [];
  filteredInvestmentRows: MarketingInvestmentDetailRow[] = [];
  filteredLeadRows: MarketingLeadDetailRow[] = [];
  filteredVisitorRows: MarketingVisitorDetailRow[] = [];
  pagedInvestmentRows: MarketingInvestmentDetailRow[] = [];
  pagedLeadRows: MarketingLeadDetailRow[] = [];
  pagedVisitorRows: MarketingVisitorDetailRow[] = [];

  loading = true;
  errorMessage = '';
  exporting = false;
  pageIndex = 0;
  pageSize = 100;

  get isInvestment(): boolean {
    return this.data.kind === 'investment';
  }

  get isLeads(): boolean {
    return this.data.kind === 'leads';
  }

  get isVisitors(): boolean {
    return this.data.kind === 'visitors';
  }

  get isBranchDetail(): boolean {
    return this.data.branchId !== undefined;
  }

  get title(): string {
    const base = this.isInvestment
      ? 'Inversión'
      : this.isLeads
        ? 'Leads'
        : 'Visitantes';
    return this.data.branchName
      ? `${base} · ${this.data.branchName}`
      : `${base} · Todas las sucursales`;
  }

  get kicker(): string {
    return this.isInvestment
      ? 'Trazabilidad de campañas Meta'
      : this.isLeads
        ? 'Trazabilidad de contactos iVentas'
        : 'Trazabilidad de visitantes únicos';
  }

  get subtitle(): string {
    if (this.isInvestment) {
      return `Campañas del Meta canónico para ${this.data.month}.`;
    }
    if (this.isLeads) {
      return `Un contacto canónico por fila para ${this.data.month}.`;
    }
    return `Identidad única por sucursal y teléfono para ${this.data.month}.`;
  }

  get exportLabel(): string {
    if (this.exporting) {
      return 'Generando…';
    }
    return this.isInvestment
      ? 'Exportar inversión'
      : this.isLeads
        ? 'Exportar leads'
        : 'Exportar visitantes';
  }

  get searchLabel(): string {
    return this.isInvestment
      ? 'Buscar campaña'
      : this.isLeads
        ? 'Buscar lead'
        : 'Buscar visitante';
  }

  get filteredCount(): number {
    if (this.isInvestment) {
      return this.filteredInvestmentRows.length;
    }
    if (this.isLeads) {
      return this.filteredLeadRows.length;
    }
    return this.filteredVisitorRows.length;
  }

  get totalCount(): number {
    if (this.isInvestment) {
      return this.investmentRows.length;
    }
    if (this.isLeads) {
      return this.leadRows.length;
    }
    return this.visitorRows.length;
  }

  get resultCountLabel(): string {
    return `${this.filteredCount} de ${this.totalCount} filas`;
  }

  get summaryCards(): MarketingDetailSummaryCard[] {
    if (this.investmentDetail) {
      const summary = this.investmentDetail.summary;
      const cards = [
        {
          label: 'Inversión del funnel',
          value: this.formatCurrency(summary.card_investment),
        },
      ];
      if (summary.total_meta_spend !== null) {
        cards.push({
          label: 'Meta total',
          value: this.formatCurrency(summary.total_meta_spend),
        });
      }
      if (summary.unassigned_spend !== null) {
        cards.push({
          label: 'Sin asignar',
          value: this.formatCurrency(summary.unassigned_spend),
        });
      }
      if (summary.conflict_spend !== null) {
        cards.push({
          label: 'Conflicto',
          value: this.formatCurrency(summary.conflict_spend),
        });
      }
      return cards;
    }
    if (this.leadsDetail) {
      return [
        {
          label: 'Leads',
          value: this.formatInteger(this.leadsDetail.summary.leads),
        },
        {
          label: 'Run iVentas',
          value: this.formatInteger(
            this.leadsDetail.source.iventas_sync_run_id,
          ),
        },
        {
          label: 'Periodo',
          value: this.leadsDetail.source.period_key,
        },
      ];
    }
    if (this.visitorsDetail) {
      const summary = this.visitorsDetail.summary;
      return [
        {
          label: 'Visitantes únicos',
          value: this.formatInteger(summary.unique_visitors),
        },
        {
          label: 'Eventos elegibles',
          value: this.formatInteger(summary.eligible_visit_events),
        },
        {
          label: 'Con teléfono válido',
          value: this.formatInteger(
            summary.visit_events_with_valid_phone,
          ),
        },
        {
          label: 'Sin teléfono válido',
          value: this.formatInteger(
            summary.visit_events_without_valid_phone,
          ),
        },
        {
          label: 'Cobertura',
          value: this.formatPercent(summary.visit_phone_coverage_rate),
        },
      ];
    }
    return [];
  }

  get investmentColumns(): string[] {
    return [
      ...(this.isBranchDetail ? [] : ['status']),
      ...(this.isBranchDetail ? [] : ['sucursal']),
      'campaign',
      'account',
      'ads',
      'leads',
      'spend',
      'delivery',
    ];
  }

  get leadColumns(): string[] {
    return [
      ...(this.isBranchDetail ? [] : ['sucursal']),
      'contact',
      'firstMessage',
      'channel',
      'metaAd',
      'campaign',
    ];
  }

  get visitorColumns(): string[] {
    return [
      ...(this.isBranchDetail ? [] : ['sucursal']),
      'phone',
      'firstVisit',
      'lastVisit',
      'events',
      'visitTypes',
    ];
  }

  ngOnInit(): void {
    this.searchControl.valueChanges
      .pipe(
        debounceTime(150),
        distinctUntilChanged(),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe(() => this.applyFilters(true));
    this.loadDetail();
  }

  loadDetail(): void {
    this.loading = true;
    this.errorMessage = '';
    if (this.isInvestment) {
      this.loadInvestment();
    } else if (this.isLeads) {
      this.loadLeads();
    } else {
      this.loadVisitors();
    }
  }

  onPage(event: PageEvent): void {
    this.pageIndex = event.pageIndex;
    this.pageSize = event.pageSize;
    this.updatePagedRows();
  }

  async exportDetail(): Promise<void> {
    if (this.exporting) {
      return;
    }
    this.exporting = true;
    try {
      if (this.investmentDetail) {
        await this.excelExport.exportInvestmentDetail(
          this.investmentDetail,
        );
      } else if (this.leadsDetail) {
        await this.excelExport.exportLeadsDetail(this.leadsDetail);
      } else if (this.visitorsDetail) {
        await this.excelExport.exportVisitorsDetail(
          this.visitorsDetail,
        );
      }
      this.snackBar.open('Excel de detalle generado.', 'Cerrar', {
        duration: 3000,
      });
    } catch {
      this.snackBar.open(
        'No fue posible generar el Excel de detalle.',
        'Cerrar',
        { duration: 4500 },
      );
    } finally {
      this.exporting = false;
    }
  }

  close(): void {
    this.dialogRef.close();
  }

  assignmentLabel(status: string): string {
    if (status === 'ASSIGNED') {
      return 'Asignada';
    }
    if (status === 'CONFLICT') {
      return 'Conflicto';
    }
    return 'Sin asignar';
  }

  trackInvestmentRow(
    _index: number,
    row: MarketingInvestmentDetailRow,
  ): string {
    return row.campaign_id;
  }

  trackLeadRow(_index: number, row: MarketingLeadDetailRow): string {
    return `${row.sucursal_id}:${row.contact_id}`;
  }

  trackVisitorRow(
    index: number,
    _row: MarketingVisitorDetailRow,
  ): number {
    return index;
  }

  formatCurrency(value: number | null): string {
    if (value === null) {
      return '—';
    }
    return new Intl.NumberFormat('es-MX', {
      style: 'currency',
      currency: 'MXN',
      maximumFractionDigits: 2,
    }).format(value);
  }

  formatInteger(value: number | null): string {
    if (value === null) {
      return '—';
    }
    return new Intl.NumberFormat('es-MX', {
      maximumFractionDigits: 0,
    }).format(value);
  }

  formatPercent(value: number | null): string {
    if (value === null) {
      return '—';
    }
    return new Intl.NumberFormat('es-MX', {
      style: 'percent',
      maximumFractionDigits: 1,
    }).format(value);
  }

  formatDate(value: string | null): string {
    if (!value) {
      return '—';
    }
    const dateValue = value.includes('T')
      ? new Date(value)
      : new Date(`${value}T12:00:00`);
    return new Intl.DateTimeFormat('es-MX', {
      dateStyle: 'medium',
      ...(value.includes('T') ? { timeStyle: 'short' } : {}),
    }).format(dateValue);
  }

  private loadInvestment(): void {
    this.marketingService
      .getInvestmentDetail(this.data.month, this.data.branchId)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (response) => {
          this.investmentDetail = response;
          this.investmentRows = response.rows;
          this.finishLoad();
        },
        error: (error: HttpErrorResponse) => this.failLoad(error),
      });
  }

  private loadLeads(): void {
    this.marketingService
      .getLeadsDetail(this.data.month, this.data.branchId)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (response) => {
          this.leadsDetail = response;
          this.leadRows = response.rows;
          this.finishLoad();
        },
        error: (error: HttpErrorResponse) => this.failLoad(error),
      });
  }

  private loadVisitors(): void {
    this.marketingService
      .getVisitorsDetail(this.data.month, this.data.branchId)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (response) => {
          this.visitorsDetail = response;
          this.visitorRows = response.rows;
          this.finishLoad();
        },
        error: (error: HttpErrorResponse) => this.failLoad(error),
      });
  }

  private finishLoad(): void {
    this.loading = false;
    this.applyFilters(true);
  }

  private failLoad(error: HttpErrorResponse): void {
    this.loading = false;
    const backendMessage = error.error?.message;
    this.errorMessage = typeof backendMessage === 'string'
      && backendMessage.trim()
      ? backendMessage.trim()
      : 'No fue posible cargar el detalle del indicador.';
  }

  private applyFilters(resetPage: boolean): void {
    const query = this.normalizeText(this.searchControl.value);
    this.filteredInvestmentRows = this.investmentRows.filter((row) =>
      this.matchesQuery(
        [
          row.assignment_status,
          row.sucursal,
          row.campaign_id,
          row.campaign_name,
          row.account_id,
          row.account_name,
        ],
        query,
      ),
    );
    this.filteredLeadRows = this.leadRows.filter((row) =>
      this.matchesQuery(
        [
          row.sucursal,
          row.contact_id,
          row.name,
          row.telefono,
          row.channel_name,
          row.channel_platform,
          ...row.meta_ad_ids,
          ...row.campaign_names,
        ],
        query,
      ),
    );
    this.filteredVisitorRows = this.visitorRows.filter((row) =>
      this.matchesQuery(
        [
          row.sucursal,
          row.telefono,
          row.first_visit_date,
          row.last_visit_date,
          ...row.visit_types,
        ],
        query,
      ),
    );
    if (resetPage) {
      this.pageIndex = 0;
    }
    this.updatePagedRows();
  }

  private updatePagedRows(): void {
    const start = this.pageIndex * this.pageSize;
    const end = start + this.pageSize;
    this.pagedInvestmentRows = this.filteredInvestmentRows.slice(start, end);
    this.pagedLeadRows = this.filteredLeadRows.slice(start, end);
    this.pagedVisitorRows = this.filteredVisitorRows.slice(start, end);
  }

  private matchesQuery(
    values: Array<string | number | null>,
    query: string,
  ): boolean {
    if (!query) {
      return true;
    }
    return this.normalizeText(
      values.map((value) => String(value ?? '')).join(' '),
    ).includes(query);
  }

  private normalizeText(value: string): string {
    return value
      .trim()
      .toLocaleLowerCase('es-MX')
      .normalize('NFD')
      .replace(/[\u0300-\u036f]/g, '');
  }
}
