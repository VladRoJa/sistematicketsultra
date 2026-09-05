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
import { MatNativeDateModule } from '@angular/material/core';
import { MatDatepickerModule } from '@angular/material/datepicker';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatPaginatorModule, PageEvent } from '@angular/material/paginator';
import { MatSelectModule } from '@angular/material/select';
import { MatSortModule, Sort } from '@angular/material/sort';
import { MatTableDataSource, MatTableModule } from '@angular/material/table';
import { MatTooltipModule } from '@angular/material/tooltip';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import {
  Subject,
  catchError,
  debounceTime,
  map,
  merge,
  of,
  switchMap,
  tap,
} from 'rxjs';

import {
  ReactivationCampaign,
  ReactivationCampaignDetail,
  ReactivationCampaignFilters,
  ReactivationCampaignPreviewResponse,
  ReactivationCampaignRequest,
  ReactivationCandidateQuery,
  ReactivationCandidateSummaryQuery,
  ReactivationCandidateSummaryResponse,
  ReactivationCandidateReason,
  ReactivationCandidateRow,
  ReactivationCandidateSort,
  ReactivationCandidatesResponse,
  ReactivationIventasPeriod,
  ReactivationOperationalStatus,
  ReactivationSourcesResponse,
  ReactivationTariffCount,
  ReactivationTariffGroup,
} from './marketing-reactivation.models';
import { MarketingReactivationService } from './marketing-reactivation.service';

type OperationalContactStatus =
  | 'NO_CONTACT_IN_PERIOD'
  | 'NO_OUTBOUND_MESSAGE'
  | 'CONTACTED_BEFORE_EXPIRATION'
  | 'CONTACTED_AFTER_EXPIRATION'
  | 'REVIEW_IDENTITY'
  | 'ACTIVE';

type StatusFilter = ReactivationOperationalStatus;

interface OperationalStatusOption {
  value: StatusFilter;
  label: string;
}

interface SummaryCard {
  label: string;
  value: number;
  displayValue?: string;
  detail?: string;
  icon: string;
  statusClass: string;
}

type SourcesRequestResult =
  | { status: 'success'; data: ReactivationSourcesResponse }
  | { status: 'error'; error: HttpErrorResponse };

type CandidatesRequestResult =
  | { status: 'success'; data: ReactivationCandidatesResponse }
  | { status: 'error'; error: HttpErrorResponse };

type SummaryRequestResult =
  | { status: 'success'; data: ReactivationCandidateSummaryResponse }
  | { status: 'error'; error: HttpErrorResponse };

const OPERATIONAL_STATUS_OPTIONS: OperationalStatusOption[] = [
  { value: 'WORK_PENDING', label: 'Por trabajar' },
  {
    value: 'NO_CONTACT_IN_PERIOD',
    label: 'No aparece en CRM este periodo',
  },
  { value: 'NO_OUTBOUND_MESSAGE', label: 'En CRM, sin mensaje enviado' },
  {
    value: 'CONTACTED_BEFORE_EXPIRATION',
    label: 'Contactado antes de vencer',
  },
  {
    value: 'CONTACTED_AFTER_EXPIRATION',
    label: 'Contactado después de vencer',
  },
  { value: 'REVIEW_IDENTITY', label: 'Revisar identidad' },
  { value: 'ACTIVE', label: 'Ya está activo' },
  { value: 'ALL', label: 'Todos' },
];

const REVIEW_IDENTITY_REASONS = new Set<ReactivationCandidateReason>([
  'ACTIVE_REVIEW',
  'AMBIGUOUS',
  'IDENTIFIER_CONFLICT',
  'NO_MX10',
  'DUPLICATE_VENCIDO_PHONE',
  'AMBIGUOUS_IVENTAS_IDENTITY',
]);


@Component({
  selector: 'app-marketing-reactivation',
  standalone: true,
  imports: [
    CommonModule,
    MatButtonModule,
    MatDatepickerModule,
    MatFormFieldModule,
    MatIconModule,
    MatInputModule,
    MatNativeDateModule,
    MatPaginatorModule,
    MatProgressSpinnerModule,
    MatSelectModule,
    MatSortModule,
    MatTableModule,
    MatTooltipModule,
    ReactiveFormsModule,
  ],
  templateUrl: './marketing-reactivation.component.html',
  styleUrls: ['./marketing-reactivation.component.css'],
})
export class MarketingReactivationComponent implements OnInit {
  private readonly destroyRef = inject(DestroyRef);
  private readonly reactivationService = inject(
    MarketingReactivationService,
  );
  private readonly candidateRequests = new Subject<ReactivationCandidateQuery>();
  private readonly summaryRequests = new Subject<ReactivationCandidateSummaryQuery>();
  private readonly cursorsByPageIndex = new Map<number, string | null>([
    [0, null],
  ]);

  readonly dateFromControl = new FormControl<Date | null>(null);
  readonly dateToControl = new FormControl<Date | null>(null);
  readonly iventasControl = new FormControl<string | null>(null);
  readonly branchFilter = new FormControl('ALL', { nonNullable: true });
  readonly tariffFilter = new FormControl('ALL', { nonNullable: true });
  readonly tariffGroupFilter = new FormControl<ReactivationTariffGroup | 'ALL'>(
    'ALL',
    { nonNullable: true },
  );
  readonly statusFilter = new FormControl<StatusFilter>('WORK_PENDING', {
    nonNullable: true,
  });
  readonly searchFilter = new FormControl('', { nonNullable: true });
  readonly statusOptions = OPERATIONAL_STATUS_OPTIONS;
  readonly tariffGroupOptions: Array<{
    value: ReactivationTariffGroup;
    label: string;
  }> = [
    { value: 'REACTIVATE', label: 'Reactivables' },
    { value: 'DOMICILIATED_FLOW', label: 'Flujo domiciliado' },
    { value: 'EXCLUDE', label: 'Excluidas' },
    { value: 'REVIEW', label: 'Por revisar' },
  ];

  readonly displayedColumns = [
    'nombre',
    'pin',
    'sucursal',
    'fecha_vencimiento',
    'fecha_ultimo_pago',
    'tarifa',
    'telefono',
    'status',
    'latest_outbound_at_utc',
  ];

  readonly dataSource = new MatTableDataSource<ReactivationCandidateRow>([]);

  sources: ReactivationSourcesResponse | null = null;
  candidates: ReactivationCandidatesResponse | null = null;
  candidateSummary: ReactivationCandidateSummaryResponse | null = null;
  tariffRows: ReactivationTariffCount[] = [];
  campaignPreview: ReactivationCampaignPreviewResponse | null = null;
  campaigns: ReactivationCampaign[] = [];
  selectedCampaign: ReactivationCampaignDetail | null = null;

  readonly campaignNameControl = new FormControl('', { nonNullable: true });
  readonly campaignNotesControl = new FormControl('', { nonNullable: true });

  loadingSources = true;
  loadingCandidates = false;
  loadingSummary = false;
  loadingTariffs = false;
  loadingPreview = false;
  creatingCampaign = false;
  loadingCampaigns = false;
  loadingCampaignDetail = false;
  campaignActionId: number | null = null;
  sourcesError = '';
  candidatesError = '';
  summaryError = '';
  campaignError = '';
  campaignSuccess = '';
  pageIndex = 0;
  pageSize = 50;
  readonly pageSizeOptions = [25, 50, 100];
  sortActive: ReactivationCandidateSort = 'fecha_vencimiento';
  sortDirection: 'asc' | 'desc' = 'desc';

  ngOnInit(): void {
    this.configureCandidateRequests();
    this.configureSummaryRequests();
    this.configureSourceSelection();
    this.configureFilters();
    this.loadSources();
  }

  get coverageMinDate(): Date | null {
    return this.parseDateOnly(this.sources?.vencidos_coverage.min_date ?? null);
  }

  get coverageMaxDate(): Date | null {
    return this.parseDateOnly(this.sources?.vencidos_coverage.max_date ?? null);
  }

  get iventasPeriods(): ReactivationIventasPeriod[] {
    return this.sources?.iventas_periods ?? [];
  }

  get canManageCampaigns(): boolean {
    return Boolean(this.sources?.permissions?.can_manage_campaigns);
  }

  get tariffOptions(): ReactivationTariffCount[] {
    return this.tariffRows.filter((row) => Boolean(row.tarifa));
  }

  get nonReactivationTariffCount(): number {
    const summary = this.campaignPreview?.summary;
    if (!summary) {
      return 0;
    }
    return Math.max(0, summary.excluded_tariff - summary.domiciliated_flow);
  }

  get hasNoSources(): boolean {
    return Boolean(
      this.sources
      && this.sources.vencidos_coverage.total_rows === 0
      && this.iventasPeriods.length === 0,
    );
  }

  get hasVencidosWithoutIventas(): boolean {
    return Boolean(
      this.sources
      && this.sources.vencidos_coverage.total_rows > 0
      && this.iventasPeriods.length === 0,
    );
  }

  get hasIventasWithoutVencidos(): boolean {
    return Boolean(
      this.sources
      && this.sources.vencidos_coverage.total_rows === 0
      && this.iventasPeriods.length > 0,
    );
  }

  get isInitialCandidateLoading(): boolean {
    return this.loadingCandidates && !this.candidates;
  }

  get visibleCount(): number {
    return this.dataSource.data.length;
  }

  get totalCount(): number {
    return this.candidateSummary?.summary.total_rows
      ?? this.candidates?.pagination.total
      ?? 0;
  }

  get usesCursorPagination(): boolean {
    return this.statusFilter.value !== 'ALL';
  }

  get branchOptions() {
    return this.sources?.branches ?? [];
  }

  get summaryCards(): SummaryCard[] {
    const summary = this.candidateSummary?.summary;
    const counts = summary?.status_counts;

    return [
      {
        label: 'Vencidos en el periodo',
        value: summary?.total_rows ?? 0,
        detail: this.formatSelectedPeriod(),
        icon: 'event',
        statusClass: 'total',
      },
      {
        label: 'Ya están activos',
        value: counts?.EXCLUDED_ACTIVE ?? 0,
        icon: 'check_circle',
        statusClass: 'active',
      },
      {
        label: 'Contactados después de vencer',
        value: counts?.EXCLUDED_POST_EXPIRATION_CONTACT ?? 0,
        icon: 'forum',
        statusClass: 'contacted',
      },
      {
        label: 'Revisar identidad',
        value: counts?.REVIEW_ACTIVE_MATCH ?? 0,
        icon: 'warning_amber',
        statusClass: 'review',
      },
      {
        label: 'Por revisar',
        value: counts?.CONTACT_HISTORY_UNKNOWN ?? 0,
        icon: 'help_outline',
        statusClass: 'unknown',
      },
    ];
  }

  loadSources(): void {
    this.loadingSources = true;
    this.sourcesError = '';

    this.reactivationService
      .getSources()
      .pipe(
        map(
          (data): SourcesRequestResult => ({
            status: 'success',
            data,
          }),
        ),
        catchError((error: HttpErrorResponse) =>
          of<SourcesRequestResult>({ status: 'error', error }),
        ),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe((result) => {
        this.loadingSources = false;

        if (result.status === 'error') {
          this.sources = null;
          this.sourcesError = this.resolveErrorMessage(
            result.error,
            'No fue posible cargar las fuentes de reactivación.',
          );
          return;
        }

        this.applySources(result.data);
      });
  }

  retryCandidates(): void {
    this.requestSelectedCandidates();
  }

  retrySummary(): void {
    this.requestSelectedSummary();
  }

  clearFilters(): void {
    this.branchFilter.setValue('ALL', { emitEvent: false });
    this.tariffFilter.setValue('ALL', { emitEvent: false });
    this.tariffGroupFilter.setValue('ALL', { emitEvent: false });
    this.statusFilter.setValue('WORK_PENDING', { emitEvent: false });
    this.searchFilter.setValue('', { emitEvent: false });
    this.resetCandidateNavigation();
    this.requestSelectedCandidates();
    this.requestSelectedSummary();
  }

  onPageChange(event: PageEvent): void {
    if (event.pageSize !== this.pageSize) {
      this.pageSize = event.pageSize;
      this.resetCandidateNavigation();
      this.requestSelectedCandidates();
      return;
    }
    if (
      this.usesCursorPagination
      && event.pageIndex > this.pageIndex
      && !this.cursorsByPageIndex.has(event.pageIndex)
    ) {
      return;
    }
    this.pageIndex = event.pageIndex;
    this.requestSelectedCandidates();
  }

  onSortChange(event: Sort): void {
    if (!event.direction || !this.isServerSort(event.active)) {
      return;
    }
    this.sortActive = event.active;
    this.sortDirection = event.direction;
    this.resetCandidateNavigation();
    this.requestSelectedCandidates();
  }

  prepareCampaign(): void {
    const request = this.buildCampaignRequest();
    if (!request) {
      return;
    }
    this.loadingPreview = true;
    this.campaignError = '';
    this.campaignSuccess = '';
    this.campaignPreview = null;
    this.reactivationService
      .previewCampaign(request)
      .pipe(
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe({
        next: (preview) => {
          this.loadingPreview = false;
          this.campaignPreview = preview;
        },
        error: (error: HttpErrorResponse) => {
          this.loadingPreview = false;
          this.campaignError = this.resolveErrorMessage(
            error,
            'No fue posible preparar el preview de campaña.',
          );
        },
      });
  }

  confirmCampaign(): void {
    if (!this.campaignPreview || this.campaignPreview.summary.eligible === 0) {
      return;
    }
    const name = this.campaignNameControl.value.trim();
    if (!name) {
      this.campaignError = 'Escribe un nombre para la campaña.';
      return;
    }
    const baseRequest = this.buildCampaignRequest();
    if (!baseRequest) {
      return;
    }
    const request: ReactivationCampaignRequest = {
      ...baseRequest,
      name,
      notes: this.campaignNotesControl.value.trim() || null,
      filters: this.campaignPreview.filters,
    };
    this.creatingCampaign = true;
    this.campaignError = '';
    this.reactivationService
      .createCampaign(request)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (response) => {
          this.creatingCampaign = false;
          this.campaignPreview = null;
          this.campaignNameControl.setValue('');
          this.campaignNotesControl.setValue('');
          this.campaignSuccess = (
            `Campaña “${response.campaign.name}” creada con `
            + `${response.campaign.recipient_count} destinatarios.`
          );
          this.loadCampaigns();
        },
        error: (error: HttpErrorResponse) => {
          this.creatingCampaign = false;
          this.campaignError = this.resolveErrorMessage(
            error,
            'No fue posible crear la campaña.',
          );
        },
      });
  }

  cancelCampaignPreview(): void {
    this.campaignPreview = null;
    this.campaignError = '';
  }

  loadCampaigns(): void {
    if (!this.canManageCampaigns) {
      return;
    }
    this.loadingCampaigns = true;
    this.reactivationService
      .getCampaigns()
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (response) => {
          this.loadingCampaigns = false;
          this.campaigns = response.rows;
        },
        error: (error: HttpErrorResponse) => {
          this.loadingCampaigns = false;
          this.campaignError = this.resolveErrorMessage(
            error,
            'No fue posible cargar el historial de campañas.',
          );
        },
      });
  }

  viewCampaign(campaign: ReactivationCampaign): void {
    this.loadingCampaignDetail = true;
    this.selectedCampaign = null;
    this.campaignError = '';
    this.reactivationService
      .getCampaign(campaign.id)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (response) => {
          this.loadingCampaignDetail = false;
          this.selectedCampaign = response.campaign;
        },
        error: (error: HttpErrorResponse) => {
          this.loadingCampaignDetail = false;
          this.campaignError = this.resolveErrorMessage(
            error,
            'No fue posible cargar el detalle de la campaña.',
          );
        },
      });
  }

  closeCampaignDetail(): void {
    this.selectedCampaign = null;
  }

  exportCampaign(campaign: ReactivationCampaign): void {
    this.campaignActionId = campaign.id;
    this.campaignError = '';
    this.reactivationService
      .exportCampaign(campaign.id)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (blob) => {
          this.campaignActionId = null;
          const url = URL.createObjectURL(blob);
          const link = document.createElement('a');
          link.href = url;
          link.download = `reactivacion_campana_${campaign.id}.xlsx`;
          link.click();
          URL.revokeObjectURL(url);
          this.loadCampaigns();
        },
        error: (error: HttpErrorResponse) => {
          this.campaignActionId = null;
          this.campaignError = this.resolveErrorMessage(
            error,
            'No fue posible exportar la campaña.',
          );
        },
      });
  }

  markCampaignSent(campaign: ReactivationCampaign): void {
    const confirmed = window.confirm(
      `¿Registrar “${campaign.name}” como enviada externamente?`,
    );
    if (!confirmed) {
      return;
    }
    this.campaignActionId = campaign.id;
    this.campaignError = '';
    this.reactivationService
      .markCampaignSent(campaign.id)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: () => {
          this.campaignActionId = null;
          this.campaignSuccess = 'La campaña quedó registrada como enviada.';
          this.loadCampaigns();
        },
        error: (error: HttpErrorResponse) => {
          this.campaignActionId = null;
          this.campaignError = this.resolveErrorMessage(
            error,
            'No fue posible marcar la campaña como enviada.',
          );
        },
      });
  }

  campaignStatusLabel(status: ReactivationCampaign['status']): string {
    const labels: Record<ReactivationCampaign['status'], string> = {
      DRAFT: 'Borrador',
      EXPORTED: 'Exportada',
      SENT: 'Enviada',
      CANCELLED: 'Cancelada',
    };
    return labels[status];
  }

  getOperationalContactStatus(
    row: ReactivationCandidateRow,
  ): OperationalContactStatus {
    if (row.operational_status) {
      return row.operational_status;
    }
    if (row.status === 'EXCLUDED_ACTIVE') {
      return 'ACTIVE';
    }

    if (
      row.status === 'REVIEW_ACTIVE_MATCH'
      || REVIEW_IDENTITY_REASONS.has(row.reason)
    ) {
      return 'REVIEW_IDENTITY';
    }

    if (row.reason === 'NO_MATCH_CURRENT_IVENTAS_RUN') {
      return 'NO_CONTACT_IN_PERIOD';
    }

    if (row.reason === 'NO_OUTBOUND_EVIDENCE') {
      return 'NO_OUTBOUND_MESSAGE';
    }

    if (row.reason === 'ONLY_PRE_EXPIRATION_OUTBOUND') {
      return 'CONTACTED_BEFORE_EXPIRATION';
    }

    if (
      row.status === 'EXCLUDED_POST_EXPIRATION_CONTACT'
      || row.reason === 'POST_EXPIRATION_OUTBOUND'
    ) {
      return 'CONTACTED_AFTER_EXPIRATION';
    }

    return 'REVIEW_IDENTITY';
  }

  getOperationalContactLabel(row: ReactivationCandidateRow): string {
    const labels: Record<OperationalContactStatus, string> = {
      NO_CONTACT_IN_PERIOD: 'No aparece en CRM este periodo',
      NO_OUTBOUND_MESSAGE: 'En CRM, sin mensaje enviado',
      CONTACTED_BEFORE_EXPIRATION: 'Contactado antes de vencer',
      CONTACTED_AFTER_EXPIRATION: 'Contactado después de vencer',
      REVIEW_IDENTITY: 'Revisar identidad',
      ACTIVE: 'Ya está activo',
    };
    return labels[this.getOperationalContactStatus(row)];
  }

  getOperationalContactIcon(row: ReactivationCandidateRow): string {
    const icons: Record<OperationalContactStatus, string> = {
      NO_CONTACT_IN_PERIOD: 'phone_disabled',
      NO_OUTBOUND_MESSAGE: 'mark_chat_unread',
      CONTACTED_BEFORE_EXPIRATION: 'forum',
      CONTACTED_AFTER_EXPIRATION: 'forum',
      REVIEW_IDENTITY: 'warning_amber',
      ACTIVE: 'check_circle',
    };
    return icons[this.getOperationalContactStatus(row)];
  }

  getOperationalContactClass(row: ReactivationCandidateRow): string {
    const classes: Record<OperationalContactStatus, string> = {
      NO_CONTACT_IN_PERIOD: 'no-contact',
      NO_OUTBOUND_MESSAGE: 'no-outbound',
      CONTACTED_BEFORE_EXPIRATION: 'contacted',
      CONTACTED_AFTER_EXPIRATION: 'contacted',
      REVIEW_IDENTITY: 'review',
      ACTIVE: 'active',
    };
    return classes[this.getOperationalContactStatus(row)];
  }

  formatIventasSource(source: ReactivationIventasPeriod): string {
    const month = this.formatMonthYear(source.date_from);
    const cutoff = this.formatShortDate(source.date_to);
    return `${month} · al ${cutoff}`;
  }

  formatDateOnly(value: string | null): string {
    const parsed = this.parseDateOnly(value);
    if (!parsed) {
      return '—';
    }

    return new Intl.DateTimeFormat('es-MX', {
      day: '2-digit',
      month: 'short',
      year: 'numeric',
    }).format(parsed);
  }

  formatDateTime(value: string | null): string {
    if (!value) {
      return '—';
    }

    const parsed = new Date(value);
    if (Number.isNaN(parsed.getTime())) {
      return '—';
    }

    return new Intl.DateTimeFormat('es-MX', {
      day: '2-digit',
      month: 'short',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
      timeZone: 'America/Tijuana',
    }).format(parsed);
  }

  adeudoTooltip(row: ReactivationCandidateRow): string {
    return row.adeudo ? `Adeudo registrado: ${row.adeudo}` : '';
  }

  trackByRowId(
    index: number,
    row: ReactivationCandidateRow,
  ): number {
    return row.vencido_row_id;
  }

  private configureCandidateRequests(): void {
    this.candidateRequests
      .pipe(
        tap(() => {
          this.loadingCandidates = true;
          this.candidatesError = '';
        }),
        switchMap((selection) =>
          this.reactivationService
            .getCandidates(selection)
            .pipe(
              map(
                (data): CandidatesRequestResult => ({
                  status: 'success',
                  data,
                }),
              ),
              catchError((error: HttpErrorResponse) =>
                of<CandidatesRequestResult>({
                  status: 'error',
                  error,
                }),
              ),
            ),
        ),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe((result) => {
        this.loadingCandidates = false;

        if (result.status === 'error') {
          this.candidatesError = this.resolveErrorMessage(
            result.error,
            'No fue posible cargar los socios para reactivación.',
          );
          return;
        }

        this.candidates = result.data;
        this.pageIndex = Math.max(0, result.data.pagination.page - 1);
        this.pageSize = result.data.pagination.page_size;
        this.dataSource.data = result.data.rows;
        if (this.usesCursorPagination) {
          const nextCursor = result.data.pagination.next_cursor;
          if (nextCursor) {
            this.cursorsByPageIndex.set(
              result.data.pagination.page,
              nextCursor,
            );
          } else {
            this.cursorsByPageIndex.delete(result.data.pagination.page);
          }
        }
      });
  }

  private configureSummaryRequests(): void {
    this.summaryRequests
      .pipe(
        tap(() => {
          this.loadingSummary = true;
          this.summaryError = '';
        }),
        switchMap((selection) =>
          this.reactivationService
            .getCandidateSummary(selection)
            .pipe(
              map(
                (data): SummaryRequestResult => ({
                  status: 'success',
                  data,
                }),
              ),
              catchError((error: HttpErrorResponse) =>
                of<SummaryRequestResult>({ status: 'error', error }),
              ),
            ),
        ),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe((result) => {
        this.loadingSummary = false;
        if (result.status === 'error') {
          this.summaryError = this.resolveErrorMessage(
            result.error,
            'No fue posible cargar el resumen del segmento.',
          );
          return;
        }
        this.candidateSummary = result.data;
      });
  }

  private configureSourceSelection(): void {
    merge(
      this.dateFromControl.valueChanges,
      this.dateToControl.valueChanges,
      this.iventasControl.valueChanges,
    )
      .pipe(
        debounceTime(0),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe(() => {
        this.campaignPreview = null;
        this.resetCandidateNavigation();
        this.requestSelectedCandidates();
        this.requestSelectedSummary();
        this.requestTariffs();
      });
  }

  private configureFilters(): void {
    merge(
      this.branchFilter.valueChanges,
      this.tariffFilter.valueChanges,
      this.tariffGroupFilter.valueChanges,
      this.statusFilter.valueChanges,
    )
      .pipe(
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe(() => {
        this.campaignPreview = null;
        this.resetCandidateNavigation();
        this.requestSelectedCandidates();
        this.requestSelectedSummary();
      });
    this.searchFilter.valueChanges
      .pipe(
        debounceTime(300),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe(() => {
        this.campaignPreview = null;
        this.resetCandidateNavigation();
        this.requestSelectedCandidates();
        this.requestSelectedSummary();
      });
  }

  private applySources(sources: ReactivationSourcesResponse): void {
    this.sources = sources;
    this.candidates = null;
    this.candidateSummary = null;
    this.dataSource.data = [];
    this.candidatesError = '';
    this.resetCandidateNavigation();

    const latestDate = this.parseDateOnly(sources.vencidos_coverage.max_date);
    const iventasPeriodKey = sources.iventas_periods[0]?.period_key ?? null;

    this.dateFromControl.setValue(latestDate, { emitEvent: false });
    this.dateToControl.setValue(latestDate, { emitEvent: false });
    this.iventasControl.setValue(iventasPeriodKey, { emitEvent: false });

    if (latestDate && iventasPeriodKey) {
      this.requestSelectedCandidates();
      this.requestSelectedSummary();
      this.requestTariffs();
    }
    if (this.canManageCampaigns) {
      this.loadCampaigns();
    }
  }

  private requestTariffs(): void {
    const dateFrom = this.dateFromControl.value;
    const dateTo = this.dateToControl.value;
    if (!dateFrom || !dateTo || dateFrom.getTime() > dateTo.getTime()) {
      return;
    }
    this.loadingTariffs = true;
    this.reactivationService
      .getTariffs(
        this.formatDateForApi(dateFrom),
        this.formatDateForApi(dateTo),
      )
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (response) => {
          this.loadingTariffs = false;
          this.tariffRows = response.rows;
          const selected = this.tariffFilter.value;
          if (
            selected !== 'ALL'
            && !response.rows.some((row) => row.tarifa === selected)
          ) {
            this.tariffFilter.setValue('ALL');
          }
        },
        error: () => {
          this.loadingTariffs = false;
          this.tariffRows = [];
        },
      });
  }

  private requestSelectedCandidates(): void {
    const dateFrom = this.dateFromControl.value;
    const dateTo = this.dateToControl.value;
    const iventasPeriodKey = this.iventasControl.value?.trim();

    if (!dateFrom || !dateTo || !iventasPeriodKey) {
      return;
    }
    if (this.dateFromControl.invalid || this.dateToControl.invalid) {
      this.candidatesError = 'Selecciona fechas dentro de la cobertura disponible.';
      return;
    }
    if (dateFrom.getTime() > dateTo.getTime()) {
      this.candidatesError = 'Desde no puede ser posterior a Hasta.';
      return;
    }

    this.candidateRequests.next({
      dateFrom: this.formatDateForApi(dateFrom),
      dateTo: this.formatDateForApi(dateTo),
      iventasPeriodKey,
      page: this.pageIndex + 1,
      pageSize: this.pageSize,
      sucursal: this.branchFilter.value === 'ALL'
        ? null
        : this.branchFilter.value,
      tarifa: this.tariffFilter.value === 'ALL'
        ? null
        : this.tariffFilter.value,
      tariffGroup: this.tariffGroupFilter.value === 'ALL'
        ? null
        : this.tariffGroupFilter.value,
      operationalStatus: this.statusFilter.value,
      search: this.searchFilter.value.trim() || null,
      sort: this.sortActive,
      direction: this.sortDirection,
      cursor: this.usesCursorPagination
        ? this.cursorsByPageIndex.get(this.pageIndex) ?? null
        : null,
    });
  }

  private requestSelectedSummary(): void {
    const selection = this.buildSummarySelection();
    if (selection) {
      this.summaryRequests.next(selection);
    }
  }

  private buildSummarySelection(): ReactivationCandidateSummaryQuery | null {
    const dateFrom = this.dateFromControl.value;
    const dateTo = this.dateToControl.value;
    const iventasPeriodKey = this.iventasControl.value?.trim();
    if (
      !dateFrom
      || !dateTo
      || !iventasPeriodKey
      || this.dateFromControl.invalid
      || this.dateToControl.invalid
      || dateFrom.getTime() > dateTo.getTime()
    ) {
      return null;
    }
    return {
      dateFrom: this.formatDateForApi(dateFrom),
      dateTo: this.formatDateForApi(dateTo),
      iventasPeriodKey,
      sucursal: this.branchFilter.value === 'ALL'
        ? null
        : this.branchFilter.value,
      tarifa: this.tariffFilter.value === 'ALL'
        ? null
        : this.tariffFilter.value,
      tariffGroup: this.tariffGroupFilter.value === 'ALL'
        ? null
        : this.tariffGroupFilter.value,
      operationalStatus: this.statusFilter.value,
      search: this.searchFilter.value.trim() || null,
    };
  }

  private resetCandidateNavigation(): void {
    this.pageIndex = 0;
    this.cursorsByPageIndex.clear();
    this.cursorsByPageIndex.set(0, null);
  }

  private buildCampaignRequest(): ReactivationCampaignRequest | null {
    const dateFrom = this.dateFromControl.value;
    const dateTo = this.dateToControl.value;
    const iventasPeriodKey = this.iventasControl.value?.trim();
    if (!dateFrom || !dateTo || !iventasPeriodKey) {
      this.campaignError = 'Selecciona el rango y el periodo iVentas.';
      return null;
    }
    if (dateFrom.getTime() > dateTo.getTime()) {
      this.campaignError = 'Desde no puede ser posterior a Hasta.';
      return null;
    }
    const filters: ReactivationCampaignFilters = {
      iventas_period_key: iventasPeriodKey,
      sucursal: this.branchFilter.value === 'ALL'
        ? null
        : this.branchFilter.value,
      operational_status: this.statusFilter.value,
      search: this.searchFilter.value.trim() || null,
      tarifa: this.tariffFilter.value === 'ALL'
        ? null
        : this.tariffFilter.value,
      tariff_group: this.tariffGroupFilter.value === 'ALL'
        ? null
        : this.tariffGroupFilter.value,
    };
    return {
      date_from: this.formatDateForApi(dateFrom),
      date_to: this.formatDateForApi(dateTo),
      filters,
    };
  }


  private isServerSort(value: string): value is ReactivationCandidateSort {
    return [
      'nombre',
      'pin',
      'sucursal',
      'fecha_vencimiento',
      'fecha_ultimo_pago',
      'tarifa',
      'telefono',
    ].includes(value);
  }

  private parseDateOnly(value: string | null): Date | null {
    if (!value) {
      return null;
    }

    const parts = value.split('-').map(Number);
    if (parts.length !== 3 || parts.some((part) => !Number.isFinite(part))) {
      return null;
    }
    return new Date(parts[0], parts[1] - 1, parts[2]);
  }

  private formatDateForApi(value: Date): string {
    const year = value.getFullYear();
    const month = String(value.getMonth() + 1).padStart(2, '0');
    const day = String(value.getDate()).padStart(2, '0');
    return `${year}-${month}-${day}`;
  }

  private formatSelectedPeriod(): string {
    const dateFrom = this.dateFromControl.value;
    const dateTo = this.dateToControl.value;
    if (!dateFrom || !dateTo) {
      return '—';
    }
    const fromIso = this.formatDateForApi(dateFrom);
    const toIso = this.formatDateForApi(dateTo);
    if (fromIso === toIso) {
      return this.formatDateOnly(fromIso);
    }
    const formatter = new Intl.DateTimeFormat('es-MX', {
      day: '2-digit',
      month: 'short',
      year: dateFrom.getFullYear() === dateTo.getFullYear()
        ? undefined
        : 'numeric',
    });
    return `${formatter.format(dateFrom)} — ${formatter.format(dateTo)}`;
  }

  private formatMonthYear(value: string): string {
    const parsed = this.parseDateOnly(value);
    if (!parsed) {
      return value;
    }
    const formatted = new Intl.DateTimeFormat('es-MX', {
      month: 'long',
      year: 'numeric',
    }).format(parsed);
    return formatted.charAt(0).toUpperCase() + formatted.slice(1);
  }

  private formatShortDate(value: string): string {
    const parsed = this.parseDateOnly(value);
    if (!parsed) {
      return value;
    }
    return new Intl.DateTimeFormat('es-MX', {
      day: '2-digit',
      month: 'short',
    }).format(parsed);
  }

  private resolveErrorMessage(
    error: HttpErrorResponse,
    fallback: string,
  ): string {
    const apiMessage = error.error?.message;
    return typeof apiMessage === 'string' && apiMessage.trim()
      ? apiMessage
      : fallback;
  }
}
