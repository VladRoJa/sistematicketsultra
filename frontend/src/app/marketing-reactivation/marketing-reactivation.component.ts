import { HttpErrorResponse } from '@angular/common/http';
import { CommonModule } from '@angular/common';
import {
  Component,
  DestroyRef,
  OnInit,
  ViewChild,
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
import { MatSelectModule } from '@angular/material/select';
import { MatSort, MatSortModule } from '@angular/material/sort';
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
  ReactivationCandidateReason,
  ReactivationCandidateRow,
  ReactivationCandidateStatus,
  ReactivationCandidatesResponse,
  ReactivationIventasPeriod,
  ReactivationSourcesResponse,
} from './marketing-reactivation.models';
import { MarketingReactivationService } from './marketing-reactivation.service';

type OperationalContactStatus =
  | 'NO_CONTACT_IN_PERIOD'
  | 'NO_OUTBOUND_MESSAGE'
  | 'CONTACTED_BEFORE_EXPIRATION'
  | 'CONTACTED_AFTER_EXPIRATION'
  | 'REVIEW_IDENTITY'
  | 'ACTIVE';

type StatusFilter = OperationalContactStatus | 'WORK_PENDING' | 'ALL';

interface OperationalStatusOption {
  value: StatusFilter;
  label: string;
}

interface CandidateSelection {
  dateFrom: string;
  dateTo: string;
  iventasPeriodKey: string;
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

const STATUS_ORDER: ReactivationCandidateStatus[] = [
  'CONTACT_HISTORY_UNKNOWN',
  'REVIEW_ACTIVE_MATCH',
  'EXCLUDED_POST_EXPIRATION_CONTACT',
  'EXCLUDED_ACTIVE',
];

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
  private readonly candidateRequests = new Subject<CandidateSelection>();

  readonly dateFromControl = new FormControl<Date | null>(null);
  readonly dateToControl = new FormControl<Date | null>(null);
  readonly iventasControl = new FormControl<string | null>(null);
  readonly branchFilter = new FormControl('ALL', { nonNullable: true });
  readonly statusFilter = new FormControl<StatusFilter>('WORK_PENDING', {
    nonNullable: true,
  });
  readonly searchFilter = new FormControl('', { nonNullable: true });
  readonly statusOptions = OPERATIONAL_STATUS_OPTIONS;

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
  allRows: ReactivationCandidateRow[] = [];

  loadingSources = true;
  loadingCandidates = false;
  sourcesError = '';
  candidatesError = '';

  @ViewChild(MatSort)
  set tableSort(sort: MatSort | undefined) {
    if (sort) {
      this.dataSource.sort = sort;
    }
  }

  constructor() {
    this.dataSource.sortingDataAccessor = (
      row: ReactivationCandidateRow,
      column: string,
    ): string | number => {
      const values: Record<string, string | number | null> = {
        nombre: row.nombre,
        pin: row.pin,
        sucursal: row.sucursal,
        fecha_vencimiento: row.fecha_vencimiento,
        fecha_ultimo_pago: row.fecha_ultimo_pago,
        tarifa: row.tarifa,
        telefono: row.telefono,
        status: this.getOperationalContactLabel(row),
        latest_outbound_at_utc: row.latest_outbound_at_utc,
      };
      return values[column] ?? '';
    };
  }

  ngOnInit(): void {
    this.configureCandidateRequests();
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
    return this.candidates?.summary.total_rows ?? 0;
  }

  get branchOptions(): string[] {
    return Array.from(
      new Set(this.allRows.map((row) => row.sucursal).filter(Boolean)),
    ).sort((left, right) => left.localeCompare(right, 'es-MX'));
  }

  get summaryCards(): SummaryCard[] {
    const summary = this.candidates?.summary;
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

  clearFilters(): void {
    this.branchFilter.setValue('ALL', { emitEvent: false });
    this.statusFilter.setValue('WORK_PENDING', { emitEvent: false });
    this.searchFilter.setValue('', { emitEvent: false });
    this.applyFilters();
  }

  getOperationalContactStatus(
    row: ReactivationCandidateRow,
  ): OperationalContactStatus {
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
            .getCandidates(
              selection.dateFrom,
              selection.dateTo,
              selection.iventasPeriodKey,
            )
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
        this.allRows = this.sortOperationally(result.data.rows);
        this.applyFilters();
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
      .subscribe(() => this.requestSelectedCandidates());
  }

  private configureFilters(): void {
    merge(
      this.branchFilter.valueChanges,
      this.statusFilter.valueChanges,
      this.searchFilter.valueChanges,
    )
      .pipe(
        debounceTime(80),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe(() => this.applyFilters());
  }

  private applySources(sources: ReactivationSourcesResponse): void {
    this.sources = sources;
    this.candidates = null;
    this.allRows = [];
    this.dataSource.data = [];
    this.candidatesError = '';

    const latestDate = this.parseDateOnly(sources.vencidos_coverage.max_date);
    const iventasPeriodKey = sources.iventas_periods[0]?.period_key ?? null;

    this.dateFromControl.setValue(latestDate, { emitEvent: false });
    this.dateToControl.setValue(latestDate, { emitEvent: false });
    this.iventasControl.setValue(iventasPeriodKey, { emitEvent: false });

    if (latestDate && iventasPeriodKey) {
      const latestDateIso = this.formatDateForApi(latestDate);
      this.candidateRequests.next({
        dateFrom: latestDateIso,
        dateTo: latestDateIso,
        iventasPeriodKey,
      });
    }
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
    });
  }

  private applyFilters(): void {
    const branch = this.branchFilter.value;
    const status = this.statusFilter.value;
    const search = this.normalizeSearch(this.searchFilter.value);

    this.dataSource.data = this.allRows.filter((row) => {
      const operationalStatus = this.getOperationalContactStatus(row);

      if (branch !== 'ALL' && row.sucursal !== branch) {
        return false;
      }
      if (
        status === 'WORK_PENDING'
        && (
          operationalStatus === 'ACTIVE'
          || operationalStatus === 'CONTACTED_AFTER_EXPIRATION'
        )
      ) {
        return false;
      }
      if (
        status !== 'ALL'
        && status !== 'WORK_PENDING'
        && operationalStatus !== status
      ) {
        return false;
      }
      if (!search) {
        return true;
      }

      return [row.nombre, row.pin, row.telefono]
        .some((value) => this.normalizeSearch(value).includes(search));
    });
  }

  private sortOperationally(
    rows: ReactivationCandidateRow[],
  ): ReactivationCandidateRow[] {
    const priority = new Map(
      STATUS_ORDER.map((status, index) => [status, index]),
    );

    return [...rows].sort((left, right) => {
      const statusDifference =
        (priority.get(left.status) ?? Number.MAX_SAFE_INTEGER)
        - (priority.get(right.status) ?? Number.MAX_SAFE_INTEGER);
      if (statusDifference !== 0) {
        return statusDifference;
      }

      const expirationDifference = right.fecha_vencimiento.localeCompare(
        left.fecha_vencimiento,
      );
      if (expirationDifference !== 0) {
        return expirationDifference;
      }

      const branchDifference = left.sucursal.localeCompare(
        right.sucursal,
        'es-MX',
      );
      if (branchDifference !== 0) {
        return branchDifference;
      }

      return (left.nombre ?? '').localeCompare(
        right.nombre ?? '',
        'es-MX',
      );
    });
  }

  private normalizeSearch(value: string | null): string {
    return String(value ?? '')
      .normalize('NFD')
      .replace(/[\u0300-\u036f]/g, '')
      .trim()
      .toLowerCase();
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
