import {
  Component,
  HostListener,
  Inject,
  OnDestroy,
  OnInit,
  Renderer2,
} from '@angular/core';
import { CommonModule, DOCUMENT } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { A11yModule } from '@angular/cdk/a11y';
import { forkJoin } from 'rxjs';

import { SessionService } from '../core/auth/session.service';
import {
  SystemDailyCheckAffectedScope,
  SystemDailyCheckAnswerPayload,
  SystemDailyCheckAnswerValue,
  SystemDailyCheckBranch,
  SystemDailyCheckGeneralStatus,
  SystemDailyCheckQuestion,
  SystemDailyCheckService,
  SystemDailyCheckStatus,
  SystemDailyCheckSubmitPayload,
} from './system-daily-check.service';
import {
  buildSystemDailyCheckQuestionGroups,
  canSystemDailyCheckPostpone,
  isSystemDailyCheckMvpCandidate,
  isSystemDailyCheckQuestionComplete,
  resolveSystemDailyCheckGatePresentation,
  SystemDailyCheckGateQuestionGroup,
  SystemDailyCheckGateScreen,
} from './system-daily-check-gate-state';

interface AnswerState {
  answer: SystemDailyCheckAnswerValue | null;
  affectedScope: SystemDailyCheckAffectedScope | null;
  reportedToSupport: boolean | null;
  description: string;
  evidence: File | null;
  evidenceError: string;
}

const MAX_EVIDENCE_BYTES = 15 * 1024 * 1024;
const ALLOWED_EVIDENCE_TYPES = new Set([
  'image/jpeg',
  'image/png',
  'image/webp',
  'application/pdf',
]);

@Component({
  selector: 'app-system-daily-check-gate',
  standalone: true,
  imports: [
    CommonModule,
    FormsModule,
    A11yModule,
  ],
  templateUrl: './system-daily-check-gate.component.html',
  styleUrls: ['./system-daily-check-gate.component.css'],
})
export class SystemDailyCheckGateComponent
  implements OnInit, OnDestroy {
  visible = false;
  loading = false;
  submitting = false;
  postponing = false;
  attemptedSubmit = false;

  screen: SystemDailyCheckGateScreen = 'branch';
  questions: SystemDailyCheckQuestion[] = [];
  questionGroups: SystemDailyCheckGateQuestionGroup<
    SystemDailyCheckQuestion
  >[] = [];
  branches: SystemDailyCheckBranch[] = [];
  selectedBranchId: number | null = null;
  status: SystemDailyCheckStatus | null = null;
  errorMessage = '';

  generalStatus: Exclude<
    SystemDailyCheckGeneralStatus,
    'NORMAL'
  > | null = null;

  private answers = new Map<string, AnswerState>();
  private refreshTimerId: ReturnType<typeof setTimeout> | null = null;
  private bootstrapRetryTimerId: ReturnType<typeof setTimeout> | null = null;
  private readonly retryDelayMs = 60 * 1000;
  private readonly maxTimerSliceMs = 60 * 1000;
  private readonly isPilotUser: boolean;

  constructor(
    private readonly checkService: SystemDailyCheckService,
    private readonly session: SessionService,
    private readonly renderer: Renderer2,
    @Inject(DOCUMENT) private readonly document: Document,
  ) {
    this.isPilotUser = isSystemDailyCheckMvpCandidate(
      this.session.getUser(),
    );
  }

  ngOnInit(): void {
    if (!this.isPilotUser) {
      return;
    }
    this.bootstrap();
  }

  ngOnDestroy(): void {
    this.clearRefreshTimer();
    this.clearBootstrapRetryTimer();
    this.unlockBackground();
  }

  @HostListener('window:focus')
  onWindowFocus(): void {
    if (
      !this.isPilotUser
      || !this.selectedBranchId
      || this.status?.completed
    ) {
      return;
    }
    this.refreshStatus(false);
  }

  @HostListener('document:keydown.escape', ['$event'])
  onEscape(event: KeyboardEvent): void {
    if (this.visible && this.status?.mandatory) {
      event.preventDefault();
      event.stopImmediatePropagation();
    }
  }

  get answeredCount(): number {
    return this.questions.filter((question) => (
      this.answerState(question.question_key).answer !== null
    )).length;
  }

  get progressPercent(): number {
    if (this.questions.length === 0) {
      return 0;
    }
    return Math.round(
      (this.answeredCount / this.questions.length) * 100,
    );
  }

  get noCount(): number {
    return this.questions.filter((question) => (
      this.answerState(question.question_key).answer === 'NO'
    )).length;
  }

  get selectedBranch(): SystemDailyCheckBranch | null {
    if (!this.selectedBranchId) {
      return null;
    }
    return this.branches.find(
      (branch) => branch.sucursal_id === this.selectedBranchId,
    ) || null;
  }

  get canSubmit(): boolean {
    if (
      this.loading
      || this.submitting
      || this.questions.length === 0
    ) {
      return false;
    }

    const allQuestionsValid = this.questions.every(
      (question) => isSystemDailyCheckQuestionComplete(
        question,
        this.answerState(question.question_key),
      ),
    );
    if (!allQuestionsValid) {
      return false;
    }

    if (this.noCount === 0) {
      return true;
    }
    return this.generalStatus !== null;
  }

  get canPostpone(): boolean {
    return canSystemDailyCheckPostpone(
      this.status,
      this.postponing || this.submitting,
    );
  }

  get isMandatory(): boolean {
    return !!this.status?.mandatory;
  }

  get introTitle(): string {
    return this.isMandatory
      ? 'Revisión diaria pendiente'
      : 'Revisión diaria de Sistemas';
  }

  get introSubtitle(): string {
    if (this.isMandatory) {
      return 'Completa la revisión para continuar usando Suite Ultra.';
    }
    if (this.status?.postpone_count === 1) {
      return 'Te queda un último aplazamiento. La revisión toma menos de un minuto.';
    }
    return 'Confirma rápidamente que los sistemas de la sucursal funcionan.';
  }

  get submitLabel(): string {
    return this.submitting
      ? 'Enviando revisión…'
      : 'Enviar revisión';
  }

  answerState(questionKey: string): AnswerState {
    let state = this.answers.get(questionKey);
    if (!state) {
      state = this.createEmptyAnswerState();
      this.answers.set(questionKey, state);
    }
    return state;
  }

  isAnswerSelected(
    questionKey: string,
    value: SystemDailyCheckAnswerValue,
  ): boolean {
    return this.answerState(questionKey).answer === value;
  }

  setAnswer(
    question: SystemDailyCheckQuestion,
    value: SystemDailyCheckAnswerValue,
  ): void {
    const state = this.answerState(question.question_key);
    state.answer = value;
    state.evidenceError = '';

    if (value !== 'NO') {
      state.affectedScope = null;
      state.reportedToSupport = null;
      state.description = '';
      state.evidence = null;
    }

    if (this.noCount === 0) {
      this.generalStatus = null;
    }
  }

  setAffectedScope(
    questionKey: string,
    value: SystemDailyCheckAffectedScope,
  ): void {
    this.answerState(questionKey).affectedScope = value;
  }

  setReportedToSupport(
    questionKey: string,
    value: boolean,
  ): void {
    this.answerState(questionKey).reportedToSupport = value;
  }

  setGeneralStatus(
    value: Exclude<SystemDailyCheckGeneralStatus, 'NORMAL'>,
  ): void {
    this.generalStatus = value;
  }

  onDescriptionChange(
    questionKey: string,
    value: string,
  ): void {
    this.answerState(questionKey).description = value;
  }

  onEvidenceSelected(
    questionKey: string,
    event: Event,
  ): void {
    const input = event.target as HTMLInputElement;
    const file = input.files?.[0] || null;
    const state = this.answerState(questionKey);
    state.evidenceError = '';

    if (!file) {
      state.evidence = null;
      return;
    }

    if (file.size > MAX_EVIDENCE_BYTES) {
      state.evidence = null;
      state.evidenceError = 'El archivo no puede superar 15 MB.';
      input.value = '';
      return;
    }

    if (
      file.type
      && !ALLOWED_EVIDENCE_TYPES.has(file.type)
    ) {
      state.evidence = null;
      state.evidenceError = 'Usa JPG, PNG, WEBP o PDF.';
      input.value = '';
      return;
    }

    state.evidence = file;
  }

  removeEvidence(questionKey: string): void {
    const state = this.answerState(questionKey);
    state.evidence = null;
    state.evidenceError = '';
  }

  chooseBranch(): void {
    this.errorMessage = '';
    if (!this.selectedBranchId) {
      this.errorMessage = 'Selecciona una sucursal para continuar.';
      return;
    }
    this.resetAnswers();
    this.refreshStatus(true);
  }

  startReview(): void {
    this.errorMessage = '';
    this.screen = 'form';
  }

  postpone(): void {
    if (!this.selectedBranchId || !this.canPostpone) {
      return;
    }

    this.postponing = true;
    this.errorMessage = '';

    this.checkService.postponeToday(
      this.selectedBranchId,
    ).subscribe({
      next: (status) => {
        this.postponing = false;
        this.applyStatus(status);
      },
      error: (error) => {
        this.postponing = false;
        this.errorMessage = this.apiErrorMessage(
          error,
          'No se pudo aplazar la revisión.',
        );
        this.refreshStatus(false, true);
      },
    });
  }

  submit(): void {
    this.attemptedSubmit = true;
    this.errorMessage = '';

    if (!this.selectedBranchId || !this.canSubmit) {
      return;
    }

    const payload = this.buildSubmitPayload();
    const evidenceByQuestion = new Map<string, File | null>();

    for (const question of this.questions) {
      const state = this.answerState(question.question_key);
      if (state.answer === 'NO') {
        evidenceByQuestion.set(
          question.question_key,
          state.evidence,
        );
      }
    }

    this.submitting = true;
    this.checkService.submitToday(
      this.selectedBranchId,
      payload,
      evidenceByQuestion,
    ).subscribe({
      next: (response) => {
        this.submitting = false;
        this.status = {
          eligible: true,
          sucursal_id: response.sucursal_id,
          business_date: response.business_date,
          completed: true,
          check_id: response.id,
          postpone_count: this.status?.postpone_count || 0,
          can_postpone: false,
          should_prompt: false,
          mandatory: false,
          next_prompt_at: null,
          mandatory_from_at: this.status?.mandatory_from_at || null,
          completed_at: response.submitted_at,
        };
        this.setVisible(false);
        this.clearRefreshTimer();
      },
      error: (error) => {
        this.submitting = false;
        this.errorMessage = this.apiErrorMessage(
          error,
          'No se pudo enviar la revisión. Tus respuestas siguen aquí.',
        );

        if (error?.status === 409) {
          this.refreshStatus(false, true);
        }
      },
    });
  }

  showQuestionError(
    question: SystemDailyCheckQuestion,
  ): boolean {
    return (
      this.attemptedSubmit
      && !isSystemDailyCheckQuestionComplete(
        question,
        this.answerState(question.question_key),
      )
    );
  }

  questionErrorText(
    question: SystemDailyCheckQuestion,
  ): string {
    const state = this.answerState(question.question_key);
    if (!state.answer) {
      return 'Selecciona Sí, No o No aplica.';
    }
    if (state.answer !== 'NO') {
      return '';
    }
    if (
      question.requires_affected_scope
      && !state.affectedScope
    ) {
      return 'Indica si afecta a uno o varios equipos.';
    }
    if (state.reportedToSupport === null) {
      return 'Indica si la falla ya fue reportada a Soporte.';
    }
    if (!state.description.trim()) {
      return 'Describe brevemente qué está pasando.';
    }
    return '';
  }

  formatBusinessDate(value: string | null | undefined): string {
    if (!value) {
      return '';
    }
    const parts = value.split('-');
    if (parts.length !== 3) {
      return value;
    }
    return `${parts[2]}/${parts[1]}/${parts[0]}`;
  }

  private bootstrap(): void {
    this.clearBootstrapRetryTimer();
    this.loading = true;
    this.errorMessage = '';

    forkJoin({
      questions: this.checkService.getQuestions(),
      branches: this.checkService.getBranches(),
    }).subscribe({
      next: ({ questions, branches }) => {
        this.loading = false;
        this.questions = questions.questions || [];
        this.questionGroups = buildSystemDailyCheckQuestionGroups(
          this.questions,
        );
        this.branches = (branches || [])
          .filter((branch) => !branch.is_demo)
          .sort((a, b) => (
            String(a.sucursal || '').localeCompare(
              String(b.sucursal || ''),
              'es',
            )
          ));
        this.initializeAnswerStates();

        const preferredBranchId = this.resolvePreferredBranchId();
        if (preferredBranchId) {
          this.selectedBranchId = preferredBranchId;
          this.refreshStatus(true);
          return;
        }

        this.screen = 'branch';
        this.setVisible(true);
      },
      error: (error) => {
        this.loading = false;
        this.setVisible(false);

        if (error?.status === 403 || error?.status === 401) {
          return;
        }
        this.scheduleBootstrapRetry();
      },
    });
  }

  private refreshStatus(
    showLoading: boolean,
    preserveError = false,
  ): void {
    if (!this.selectedBranchId) {
      return;
    }

    if (showLoading) {
      this.loading = true;
    }
    if (!preserveError) {
      this.errorMessage = '';
    }

    this.checkService.getTodayStatus(
      this.selectedBranchId,
    ).subscribe({
      next: (status) => {
        this.loading = false;
        this.applyStatus(status);
      },
      error: (error) => {
        this.loading = false;

        if (error?.status === 403 || error?.status === 401) {
          this.setVisible(false);
          return;
        }

        if (!preserveError) {
          this.errorMessage = this.apiErrorMessage(
            error,
            'No se pudo consultar la revisión diaria.',
          );
        }

        if (this.status?.mandatory) {
          this.setVisible(true);
          this.screen = 'form';
        } else {
          this.setVisible(false);
        }
        this.scheduleStatusRetry();
      },
    });
  }

  private applyStatus(status: SystemDailyCheckStatus): void {
    this.status = status;
    this.clearRefreshTimer();

    const presentation = resolveSystemDailyCheckGatePresentation(
      status,
      this.screen,
    );

    this.screen = presentation.screen;
    this.setVisible(presentation.visible);

    if (presentation.scheduleRetry) {
      this.scheduleStatusRetry(status.next_prompt_at);
    }
  }

  private scheduleStatusRetry(
    nextPromptAt?: string | null,
  ): void {
    this.clearRefreshTimer();

    let delayMs = this.maxTimerSliceMs;
    if (nextPromptAt) {
      const parsed = Date.parse(nextPromptAt);
      if (Number.isFinite(parsed)) {
        delayMs = Math.max(
          1000,
          Math.min(
            parsed - Date.now() + 500,
            this.maxTimerSliceMs,
          ),
        );
      }
    }

    this.refreshTimerId = setTimeout(() => {
      this.refreshTimerId = null;
      this.refreshStatus(false);
    }, delayMs);
  }

  private scheduleBootstrapRetry(): void {
    this.clearBootstrapRetryTimer();
    this.bootstrapRetryTimerId = setTimeout(() => {
      this.bootstrapRetryTimerId = null;
      this.bootstrap();
    }, this.retryDelayMs);
  }

  private clearRefreshTimer(): void {
    if (this.refreshTimerId !== null) {
      clearTimeout(this.refreshTimerId);
      this.refreshTimerId = null;
    }
  }

  private clearBootstrapRetryTimer(): void {
    if (this.bootstrapRetryTimerId !== null) {
      clearTimeout(this.bootstrapRetryTimerId);
      this.bootstrapRetryTimerId = null;
    }
  }

  private setVisible(value: boolean): void {
    this.visible = value;
    if (value) {
      this.lockBackground();
    } else {
      this.unlockBackground();
    }
  }

  private lockBackground(): void {
    this.renderer.setStyle(
      this.document.body,
      'overflow',
      'hidden',
    );
  }

  private unlockBackground(): void {
    this.renderer.removeStyle(
      this.document.body,
      'overflow',
    );
  }

  private initializeAnswerStates(): void {
    const next = new Map<string, AnswerState>();
    for (const question of this.questions) {
      next.set(
        question.question_key,
        this.answers.get(question.question_key)
          || this.createEmptyAnswerState(),
      );
    }
    this.answers = next;
  }

  private resetAnswers(): void {
    this.answers = new Map<string, AnswerState>();
    this.initializeAnswerStates();
    this.generalStatus = null;
    this.attemptedSubmit = false;
  }

  private createEmptyAnswerState(): AnswerState {
    return {
      answer: null,
      affectedScope: null,
      reportedToSupport: null,
      description: '',
      evidence: null,
      evidenceError: '',
    };
  }

  private buildSubmitPayload(): SystemDailyCheckSubmitPayload {
    const answers: SystemDailyCheckAnswerPayload[] = (
      this.questions.map((question) => {
        const state = this.answerState(question.question_key);
        const row: SystemDailyCheckAnswerPayload = {
          question_key: question.question_key,
          answer: state.answer as SystemDailyCheckAnswerValue,
        };

        if (state.answer === 'NO') {
          row.issue = {
            reported_to_support: state.reportedToSupport as boolean,
            description: state.description.trim(),
          };
          if (question.requires_affected_scope) {
            row.issue.affected_scope = state.affectedScope;
          }
        }
        return row;
      })
    );

    return {
      answers,
      general_status: this.noCount === 0
        ? 'NORMAL'
        : this.generalStatus as Exclude<
          SystemDailyCheckGeneralStatus,
          'NORMAL'
        >,
    };
  }

  private resolvePreferredBranchId(): number | null {
    const user = this.session.getUser();
    const sessionBranchId = Number(user?.sucursal_id || 0);

    if (
      sessionBranchId > 0
      && this.branches.some(
        (branch) => branch.sucursal_id === sessionBranchId,
      )
    ) {
      return sessionBranchId;
    }

    if (this.branches.length === 1) {
      return this.branches[0].sucursal_id;
    }

    return null;
  }

  private apiErrorMessage(
    error: any,
    fallback: string,
  ): string {
    return (
      error?.error?.detail
      || error?.error?.mensaje
      || error?.error?.message
      || fallback
    );
  }
}
