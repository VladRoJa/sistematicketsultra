import { CommonModule } from '@angular/common';
import {
  Component,
  OnDestroy,
  OnInit,
} from '@angular/core';
import { DomSanitizer, SafeResourceUrl } from '@angular/platform-browser';
import { FormsModule } from '@angular/forms';
import { BarChart, LineChart } from 'echarts/charts';
import {
  AriaComponent,
  GridComponent,
  LegendComponent,
  TooltipComponent,
} from 'echarts/components';
import * as echarts from 'echarts/core';
import { EChartsOption } from 'echarts';
import { CanvasRenderer } from 'echarts/renderers';
import {
  NgxEchartsDirective,
  provideEchartsCore,
} from 'ngx-echarts';
import {
  finalize,
  forkJoin,
} from 'rxjs';

import {
  buildSystemDailyCheckRolloutSelection,
  formatSystemDailyCheckBusinessDate,
  resolveSystemDailyCheckQuickRange,
  SystemDailyCheckQuickRange,
  systemDailyCheckMatrixTone,
  toggleSystemDailyCheckRolloutSelection,
} from './system-daily-check-bi-state';
import {
  SystemDailyCheckAnswerValue as SystemDailyCheckBiAnswer,
  SystemDailyCheckAttachment as SystemDailyCheckBiAttachment,
  SystemDailyCheckBranch as SystemDailyCheckBiBranch,
  SystemDailyCheckBiContext,
  SystemDailyCheckDetail as SystemDailyCheckBiDetail,
  SystemDailyCheckGeneralStatus as SystemDailyCheckBiGeneralStatus,
  SystemDailyCheckGranularity as SystemDailyCheckBiGranularity,
  SystemDailyCheckHistory as SystemDailyCheckBiHistory,
  SystemDailyCheckIssuesDrilldown as SystemDailyCheckBiIssuesDrilldown,
  SystemDailyCheckMatrix as SystemDailyCheckBiMatrix,
  SystemDailyCheckMatrixCell as SystemDailyCheckBiMatrixCell,
  SystemDailyCheckPending as SystemDailyCheckBiPending,
  SystemDailyCheckQuestionRanking as SystemDailyCheckBiQuestionRanking,
  SystemDailyCheckRecurrence as SystemDailyCheckBiRecurrence,
  SystemDailyCheckSummary as SystemDailyCheckBiSummary,
  SystemDailyCheckTrends as SystemDailyCheckBiTrends,
} from './system-daily-check-bi.models';
import { SystemDailyCheckBiService } from './system-daily-check-bi.service';

echarts.use([
  BarChart,
  LineChart,
  GridComponent,
  LegendComponent,
  TooltipComponent,
  AriaComponent,
  CanvasRenderer,
]);

@Component({
  selector: 'app-system-daily-check-bi',
  standalone: true,
  imports: [
    CommonModule,
    FormsModule,
    NgxEchartsDirective,
  ],
  templateUrl: './system-daily-check-bi.component.html',
  styleUrls: ['./system-daily-check-bi.component.css'],
  providers: [provideEchartsCore({ echarts })],
})
export class SystemDailyCheckBiComponent
  implements OnInit, OnDestroy {
  context: SystemDailyCheckBiContext | null = null;
  todaySummary: SystemDailyCheckBiSummary | null = null;
  matrix: SystemDailyCheckBiMatrix | null = null;
  trends: SystemDailyCheckBiTrends | null = null;
  history: SystemDailyCheckBiHistory | null = null;
  pending: SystemDailyCheckBiPending | null = null;
  issues: SystemDailyCheckBiIssuesDrilldown | null = null;
  detail: SystemDailyCheckBiDetail | null = null;

  loadingContext = true;
  loadingData = false;
  loadingHistory = false;
  loadingPending = false;
  loadingIssues = false;
  loadingDetail = false;
  savingRollout = false;
  exportingExcel = false;
  errorMessage = '';
  rolloutMessage = '';

  dateFrom = '';
  dateTo = '';
  selectedBranchId: number | null = null;
  granularity: SystemDailyCheckBiGranularity = 'DAY';
  quickRange: SystemDailyCheckQuickRange = '30D';

  historyStatus: SystemDailyCheckBiGeneralStatus | null = null;
  historyQuestionKey: string | null = null;
  historyAnswer: SystemDailyCheckBiAnswer | null = null;
  historyPage = 1;
  readonly historyPageSize = 25;

  rolloutSelection = new Set<number>();

  pendingOpen = false;
  issuesOpen = false;
  issuesTitle = '';
  detailOpen = false;
  rolloutOpen = false;
  evidenceOpen = false;
  evidenceLoading = false;
  evidenceName = '';
  evidenceMime = '';
  evidenceObjectUrl = '';
  evidenceSafeUrl: SafeResourceUrl | null = null;

  complianceChartOption: EChartsOption = {};
  failuresChartOption: EChartsOption = {};

  constructor(
    private readonly biService: SystemDailyCheckBiService,
    private readonly sanitizer: DomSanitizer,
  ) {}

  ngOnInit(): void {
    this.loadContext();
  }

  ngOnDestroy(): void {
    this.revokeEvidenceUrl();
  }

  get businessDate(): string {
    return this.context?.business_date || '';
  }

  get potentialBranches(): SystemDailyCheckBiBranch[] {
    return this.context?.universe.potential_branches || [];
  }

  get expectedBranches(): SystemDailyCheckBiBranch[] {
    return this.context?.universe.expected_branches || [];
  }

  get selectedBranchLabel(): string {
    if (!this.selectedBranchId) {
      return 'Todas las participantes';
    }
    return this.potentialBranches.find(
      (branch) => branch.sucursal_id === this.selectedBranchId,
    )?.sucursal || 'Sucursal';
  }

  get historyTotalPages(): number {
    if (!this.history) {
      return 1;
    }
    return Math.max(
      1,
      Math.ceil(
        this.history.total / this.history.page_size,
      ),
    );
  }

  get rolloutDirty(): boolean {
    const expected = new Set(
      this.expectedBranches.map(
        (branch) => branch.sucursal_id,
      ),
    );
    if (expected.size !== this.rolloutSelection.size) {
      return true;
    }
    return Array.from(expected).some(
      (id) => !this.rolloutSelection.has(id),
    );
  }

  get hasTrendData(): boolean {
    return Boolean(this.trends?.trend.length);
  }

  get topQuestionRanking(): SystemDailyCheckBiQuestionRanking[] {
    return (this.trends?.question_ranking || []).slice(0, 8);
  }

  get topRecurrence(): SystemDailyCheckBiRecurrence[] {
    return (this.trends?.recurrence || []).slice(0, 8);
  }

  loadContext(): void {
    this.loadingContext = true;
    this.errorMessage = '';

    this.biService.getContext()
      .pipe(finalize(() => {
        this.loadingContext = false;
      }))
      .subscribe({
        next: (context) => {
          this.context = context;
          this.rolloutSelection =
            buildSystemDailyCheckRolloutSelection(
              context.universe.expected_branches,
            );

          const range = resolveSystemDailyCheckQuickRange(
            context.business_date,
            '30D',
          );
          this.dateFrom = range.dateFrom;
          this.dateTo = range.dateTo;
          this.loadDashboard();
        },
        error: (error) => {
          this.errorMessage = this.apiErrorMessage(
            error,
            'No se pudo abrir Salud de Sistemas.',
          );
        },
      });
  }

  loadDashboard(): void {
    if (!this.context || !this.validateRange()) {
      return;
    }

    this.loadingData = true;
    this.errorMessage = '';

    forkJoin({
      todaySummary: this.biService.getSummary({
        dateFrom: this.businessDate,
        dateTo: this.businessDate,
        branchId: this.selectedBranchId,
      }),
      matrix: this.biService.getMatrix(
        this.businessDate,
        this.selectedBranchId,
      ),
      trends: this.biService.getTrends(
        {
          dateFrom: this.dateFrom,
          dateTo: this.dateTo,
          branchId: this.selectedBranchId,
        },
        this.granularity,
      ),
      history: this.biService.getHistory(
        {
          dateFrom: this.dateFrom,
          dateTo: this.dateTo,
          branchId: this.selectedBranchId,
        },
        {
          generalStatus: this.historyStatus,
          questionKey: this.historyQuestionKey,
          answer: this.historyAnswer,
          page: this.historyPage,
          pageSize: this.historyPageSize,
        },
      ),
    })
      .pipe(finalize(() => {
        this.loadingData = false;
      }))
      .subscribe({
        next: ({
          todaySummary,
          matrix,
          trends,
          history,
        }) => {
          this.todaySummary = todaySummary;
          this.matrix = matrix;
          this.trends = trends;
          this.history = history;
          this.buildCharts();
        },
        error: (error) => {
          this.errorMessage = this.apiErrorMessage(
            error,
            'No se pudo cargar la información de salud.',
          );
        },
      });
  }

  applyFilters(): void {
    this.historyPage = 1;
    this.loadDashboard();
  }

  exportExcel(): void {
    if (this.exportingExcel || !this.validateRange()) {
      return;
    }

    this.exportingExcel = true;
    this.errorMessage = '';

    this.biService.exportExcel({
      dateFrom: this.dateFrom,
      dateTo: this.dateTo,
      branchId: this.selectedBranchId,
    })
      .pipe(finalize(() => {
        this.exportingExcel = false;
      }))
      .subscribe({
        next: (response) => {
          if (!response.body) {
            this.errorMessage =
              'El reporte Excel llegó vacío.';
            return;
          }

          const contentDisposition = (
            response.headers.get('content-disposition')
            || ''
          );
          const filename = this.exportFilename(
            contentDisposition,
          );
          const objectUrl = URL.createObjectURL(
            response.body,
          );
          const anchor = document.createElement('a');
          anchor.href = objectUrl;
          anchor.download = filename;
          anchor.rel = 'noopener';
          anchor.click();
          URL.revokeObjectURL(objectUrl);
        },
        error: (error) => {
          this.errorMessage = this.apiErrorMessage(
            error,
            'No se pudo generar el reporte Excel.',
          );
        },
      });
  }

  private exportFilename(
    contentDisposition: string,
  ): string {
    const utf8Match = /filename\*=UTF-8''([^;]+)/i.exec(
      contentDisposition,
    );
    if (utf8Match?.[1]) {
      try {
        return decodeURIComponent(utf8Match[1]);
      } catch {
        return utf8Match[1];
      }
    }

    const regularMatch = /filename="?([^";]+)"?/i.exec(
      contentDisposition,
    );
    if (regularMatch?.[1]) {
      return regularMatch[1];
    }

    return (
      'salud_sistemas_'
      + this.dateFrom
      + '_'
      + this.dateTo
      + '.xlsx'
    );
  }

  setQuickRange(range: SystemDailyCheckQuickRange): void {
    if (!this.context) {
      return;
    }
    const resolved = resolveSystemDailyCheckQuickRange(
      this.context.business_date,
      range,
    );
    this.quickRange = range;
    this.dateFrom = resolved.dateFrom;
    this.dateTo = resolved.dateTo;
    this.historyPage = 1;
    this.loadDashboard();
  }

  setBranch(value: string | number | null): void {
    if (value === null || value === '') {
      this.selectedBranchId = null;
    } else {
      const parsed = Number(value);
      this.selectedBranchId = Number.isFinite(parsed)
        ? parsed
        : null;
    }
    this.onBranchChange();
  }

  onBranchChange(): void {
    this.historyPage = 1;
    this.loadDashboard();
  }

  onGranularityChange(): void {
    this.loadDashboard();
  }

  clearHistoryFilters(): void {
    this.historyStatus = null;
    this.historyQuestionKey = null;
    this.historyAnswer = null;
    this.historyPage = 1;
    this.loadHistory();
  }

  applyHistoryFilters(): void {
    this.historyPage = 1;
    this.loadHistory();
  }

  loadHistory(): void {
    if (!this.validateRange()) {
      return;
    }
    this.loadingHistory = true;
    this.errorMessage = '';

    this.biService.getHistory(
      {
        dateFrom: this.dateFrom,
        dateTo: this.dateTo,
        branchId: this.selectedBranchId,
      },
      {
        generalStatus: this.historyStatus,
        questionKey: this.historyQuestionKey,
        answer: this.historyAnswer,
        page: this.historyPage,
        pageSize: this.historyPageSize,
      },
    )
      .pipe(finalize(() => {
        this.loadingHistory = false;
      }))
      .subscribe({
        next: (history) => {
          this.history = history;
        },
        error: (error) => {
          this.errorMessage = this.apiErrorMessage(
            error,
            'No se pudo cargar el historial.',
          );
        },
      });
  }

  historyPreviousPage(): void {
    if (!this.history || this.historyPage <= 1) {
      return;
    }
    this.historyPage -= 1;
    this.loadHistory();
  }

  historyNextPage(): void {
    if (
      !this.history
      || this.historyPage >= this.historyTotalPages
    ) {
      return;
    }
    this.historyPage += 1;
    this.loadHistory();
  }

  openTodayHistory(
    status: SystemDailyCheckBiGeneralStatus | null,
  ): void {
    this.dateFrom = this.businessDate;
    this.dateTo = this.businessDate;
    this.quickRange = 'TODAY';
    this.historyStatus = status;
    this.historyQuestionKey = null;
    this.historyAnswer = null;
    this.historyPage = 1;
    this.loadDashboard();
  }

  openTodayPending(): void {
    this.openPendingFor(
      this.businessDate,
      this.businessDate,
      this.selectedBranchId,
    );
  }

  openPendingBranch(branchId: number): void {
    this.openPendingFor(
      this.businessDate,
      this.businessDate,
      branchId,
    );
  }

  drillQuestion(questionKey: string): void {
    this.historyQuestionKey = questionKey;
    this.historyAnswer = 'NO';
    this.historyPage = 1;
    this.loadHistory();
  }

  drillBranch(branchId: number): void {
    this.selectedBranchId = branchId;
    this.historyPage = 1;
    this.loadDashboard();
  }

  drillRecurrence(
    item: SystemDailyCheckBiRecurrence,
  ): void {
    this.selectedBranchId = item.sucursal_id;
    this.dateFrom = item.first_business_date;
    this.dateTo = item.last_business_date;
    this.historyQuestionKey = item.question_key;
    this.historyAnswer = 'NO';
    this.historyPage = 1;
    this.loadDashboard();
  }

  openMatrixRow(
    row: NonNullable<SystemDailyCheckBiMatrix['rows']>[number],
  ): void {
    if (row.check_id) {
      this.openDetail(row.check_id);
      return;
    }
    this.openPendingBranch(row.sucursal_id);
  }

  toggleRolloutPanel(): void {
    this.rolloutOpen = !this.rolloutOpen;
    this.rolloutMessage = '';
  }

  private openPendingFor(
    dateFrom: string,
    dateTo: string,
    branchId: number | null,
  ): void {
    if (!this.context) {
      return;
    }
    this.loadingPending = true;
    this.pendingOpen = true;
    this.pending = null;

    this.biService.getPending(
      {
        dateFrom,
        dateTo,
        branchId,
      },
      1,
      100,
    )
      .pipe(finalize(() => {
        this.loadingPending = false;
      }))
      .subscribe({
        next: (pending) => {
          this.pending = pending;
        },
        error: (error) => {
          this.errorMessage = this.apiErrorMessage(
            error,
            'No se pudo cargar el detalle de pendientes.',
          );
        },
      });
  }

  closePending(): void {
    this.pendingOpen = false;
  }


  openSupportIssues(reportedToSupport: boolean): void {
    this.issuesOpen = true;
    this.loadingIssues = true;
    this.issues = null;
    this.issuesTitle = reportedToSupport
      ? 'Incidencias reportadas a Soporte'
      : 'Incidencias no reportadas a Soporte';

    this.biService.getIssues(
      {
        dateFrom: this.businessDate,
        dateTo: this.businessDate,
        branchId: this.selectedBranchId,
      },
      reportedToSupport,
    )
      .pipe(finalize(() => {
        this.loadingIssues = false;
      }))
      .subscribe({
        next: (issues) => {
          this.issues = issues;
        },
        error: (error) => {
          this.errorMessage = this.apiErrorMessage(
            error,
            'No se pudo cargar el detalle de incidencias.',
          );
          this.issuesOpen = false;
        },
      });
  }

  closeIssues(): void {
    this.issuesOpen = false;
    this.issues = null;
  }

  openIssueCheck(checkId: number): void {
    this.closeIssues();
    this.openDetail(checkId);
  }

  openDetail(checkId: number): void {
    this.detailOpen = true;
    this.loadingDetail = true;
    this.detail = null;

    this.biService.getDetail(checkId)
      .pipe(finalize(() => {
        this.loadingDetail = false;
      }))
      .subscribe({
        next: (detail) => {
          this.detail = detail;
        },
        error: (error) => {
          this.errorMessage = this.apiErrorMessage(
            error,
            'No se pudo abrir el checklist.',
          );
          this.detailOpen = false;
        },
      });
  }

  closeDetail(): void {
    this.detailOpen = false;
    this.detail = null;
    this.closeEvidence();
  }

  openEvidence(
    attachment: SystemDailyCheckBiAttachment,
  ): void {
    this.evidenceOpen = true;
    this.evidenceLoading = true;
    this.evidenceName = attachment.original_filename;
    this.evidenceMime = attachment.mime_type;
    this.revokeEvidenceUrl();

    this.biService.getAttachment(attachment.id)
      .pipe(finalize(() => {
        this.evidenceLoading = false;
      }))
      .subscribe({
        next: (blob) => {
          this.evidenceObjectUrl = URL.createObjectURL(blob);
          this.evidenceSafeUrl =
            this.sanitizer.bypassSecurityTrustResourceUrl(
              this.evidenceObjectUrl,
            );
        },
        error: (error) => {
          this.errorMessage = this.apiErrorMessage(
            error,
            'No se pudo abrir la evidencia.',
          );
          this.evidenceOpen = false;
        },
      });
  }

  closeEvidence(): void {
    this.evidenceOpen = false;
    this.evidenceLoading = false;
    this.evidenceName = '';
    this.evidenceMime = '';
    this.revokeEvidenceUrl();
  }

  downloadEvidence(): void {
    if (!this.evidenceObjectUrl || !this.evidenceName) {
      return;
    }
    const anchor = document.createElement('a');
    anchor.href = this.evidenceObjectUrl;
    anchor.download = this.evidenceName;
    anchor.rel = 'noopener';
    anchor.click();
  }

  get isEvidenceImage(): boolean {
    return this.evidenceMime.startsWith('image/');
  }

  get isEvidencePdf(): boolean {
    return this.evidenceMime === 'application/pdf';
  }

  toggleRolloutBranch(branchId: number): void {
    if (this.savingRollout) {
      return;
    }
    this.rolloutSelection =
      toggleSystemDailyCheckRolloutSelection(
        this.rolloutSelection,
        branchId,
      );
    this.rolloutMessage = '';
  }

  isRolloutSelected(branchId: number): boolean {
    return this.rolloutSelection.has(branchId);
  }

  saveRollout(): void {
    if (!this.context || !this.rolloutDirty) {
      return;
    }
    this.savingRollout = true;
    this.rolloutMessage = '';
    const selectedIds = Array.from(
      this.rolloutSelection,
    ).sort((a, b) => a - b);

    this.biService.replaceRollout(selectedIds)
      .pipe(finalize(() => {
        this.savingRollout = false;
      }))
      .subscribe({
        next: (response) => {
          this.context = {
            ...this.context as SystemDailyCheckBiContext,
            universe: response.universe,
          };
          this.rolloutSelection =
            buildSystemDailyCheckRolloutSelection(
              response.universe.expected_branches,
            );
          this.rolloutMessage =
            'Participantes actualizados desde el día de negocio actual.';
          this.loadDashboard();
        },
        error: (error) => {
          this.errorMessage = this.apiErrorMessage(
            error,
            'No se pudo actualizar el rollout.',
          );
        },
      });
  }

  matrixCellClass(
    cell: SystemDailyCheckBiMatrixCell | undefined,
  ): string {
    if (!cell) {
      return 'matrix-cell--unknown';
    }
    return `matrix-cell--${systemDailyCheckMatrixTone(cell.state)}`;
  }

  generalStatusClass(
    status: SystemDailyCheckBiGeneralStatus | null | undefined,
  ): string {
    if (status === 'NORMAL') {
      return 'status-chip--normal';
    }
    if (status === 'MINOR_FAILURE') {
      return 'status-chip--warning';
    }
    if (status === 'OPERATIONAL_IMPACT') {
      return 'status-chip--critical';
    }
    return 'status-chip--neutral';
  }

  answerClass(
    answer: SystemDailyCheckBiAnswer,
  ): string {
    if (answer === 'YES') {
      return 'answer-chip--yes';
    }
    if (answer === 'NO') {
      return 'answer-chip--no';
    }
    return 'answer-chip--na';
  }

  generalStatusLabel(
    status: SystemDailyCheckBiGeneralStatus | null | undefined,
  ): string {
    if (status === 'NORMAL') {
      return 'Operación normal';
    }
    if (status === 'MINOR_FAILURE') {
      return 'Falla menor';
    }
    if (status === 'OPERATIONAL_IMPACT') {
      return 'Afecta operación';
    }
    return 'Pendiente';
  }

  answerLabel(
    answer: SystemDailyCheckBiAnswer,
  ): string {
    if (answer === 'YES') {
      return 'Sí';
    }
    if (answer === 'NO') {
      return 'No';
    }
    return 'No aplica';
  }

  formatBusinessDate(
    value: string | null | undefined,
  ): string {
    return formatSystemDailyCheckBusinessDate(value);
  }

  formatTimestamp(
    value: string | null | undefined,
  ): string {
    if (!value) {
      return '—';
    }
    const parsed = new Date(value);
    if (Number.isNaN(parsed.getTime())) {
      return value;
    }
    return new Intl.DateTimeFormat('es-MX', {
      dateStyle: 'short',
      timeStyle: 'short',
    }).format(parsed);
  }

  formatPercent(
    value: number | null | undefined,
  ): string {
    return value === null || value === undefined
      ? 'N/D'
      : `${value.toFixed(1)}%`;
  }

  formatFileSize(bytes: number): string {
    if (!Number.isFinite(bytes) || bytes <= 0) {
      return '0 KB';
    }
    if (bytes < 1024 * 1024) {
      return `${Math.max(1, Math.round(bytes / 1024))} KB`;
    }
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  }

  private buildCharts(): void {
    const trend = this.trends?.trend || [];
    const categories = trend.map((point) => (
      this.granularity === 'DAY'
        ? this.formatBusinessDate(point.period_start)
        : `${this.formatBusinessDate(point.period_start)}–${this.formatBusinessDate(point.period_end)}`
    ));

    this.complianceChartOption = {
      aria: {
        enabled: true,
        description: (
          'Tendencia de cumplimiento con checklists completados y pendientes.'
        ),
      },
      tooltip: { trigger: 'axis' },
      legend: {
        data: ['Cumplimiento', 'Completados', 'Pendientes'],
      },
      grid: {
        left: 48,
        right: 42,
        top: 52,
        bottom: 58,
        containLabel: true,
      },
      xAxis: {
        type: 'category',
        data: categories,
        axisLabel: {
          rotate: categories.length > 8 ? 35 : 0,
        },
      },
      yAxis: [
        {
          type: 'value',
          min: 0,
          max: 100,
          name: '%',
        },
        {
          type: 'value',
          min: 0,
          name: 'Checklists',
        },
      ],
      series: [
        {
          name: 'Cumplimiento',
          type: 'line',
          yAxisIndex: 0,
          smooth: true,
          data: trend.map(
            (point) => point.compliance_pct,
          ),
        },
        {
          name: 'Completados',
          type: 'bar',
          yAxisIndex: 1,
          data: trend.map(
            (point) => point.completed,
          ),
        },
        {
          name: 'Pendientes',
          type: 'bar',
          yAxisIndex: 1,
          data: trend.map(
            (point) => point.pending,
          ),
        },
      ],
    };

    this.failuresChartOption = {
      aria: {
        enabled: true,
        description: (
          'Tendencia de respuestas con falla y reporte a soporte.'
        ),
      },
      tooltip: { trigger: 'axis' },
      legend: {
        data: ['Respuestas No', 'Reportadas', 'No reportadas'],
      },
      grid: {
        left: 48,
        right: 28,
        top: 52,
        bottom: 58,
        containLabel: true,
      },
      xAxis: {
        type: 'category',
        data: categories,
        axisLabel: {
          rotate: categories.length > 8 ? 35 : 0,
        },
      },
      yAxis: {
        type: 'value',
        min: 0,
      },
      series: [
        {
          name: 'Respuestas No',
          type: 'line',
          smooth: true,
          data: trend.map(
            (point) => point.no_answers,
          ),
        },
        {
          name: 'Reportadas',
          type: 'bar',
          data: trend.map(
            (point) => point.reported,
          ),
        },
        {
          name: 'No reportadas',
          type: 'bar',
          data: trend.map(
            (point) => point.unreported,
          ),
        },
      ],
    };
  }

  private validateRange(): boolean {
    if (!this.dateFrom || !this.dateTo) {
      this.errorMessage = 'Selecciona un rango de fechas.';
      return false;
    }
    if (this.dateFrom > this.dateTo) {
      this.errorMessage =
        'La fecha inicial no puede ser posterior a la final.';
      return false;
    }
    if (this.context && this.dateTo > this.context.business_date) {
      this.errorMessage =
        'La fecha final no puede ser posterior al día de negocio actual.';
      return false;
    }
    return true;
  }

  private revokeEvidenceUrl(): void {
    if (this.evidenceObjectUrl) {
      URL.revokeObjectURL(this.evidenceObjectUrl);
    }
    this.evidenceObjectUrl = '';
    this.evidenceSafeUrl = null;
  }

  private apiErrorMessage(
    error: any,
    fallback: string,
  ): string {
    return (
      error?.error?.detail
      || error?.error?.message
      || error?.error?.mensaje
      || fallback
    );
  }
}
