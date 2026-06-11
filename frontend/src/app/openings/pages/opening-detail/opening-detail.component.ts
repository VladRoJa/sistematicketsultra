//   frontend\src\app\openings\pages\opening-detail\opening-detail.component.ts


import { CommonModule } from '@angular/common';
import { Component, ElementRef, OnDestroy, OnInit, ViewChild } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, Router } from '@angular/router';
import { forkJoin, Subscription } from 'rxjs';

import {
  Opening,
  OpeningDependencyType,
  OpeningPhase,
  OpeningTask,
  OpeningTaskComment,
  OpeningTaskDependency,
  OpeningTaskPriority,
  OpeningTaskStatus,
  OpeningTaskBlocker,
  OpeningTaskBlockerImpact,
  OpeningTaskBlockerType,
  OpeningTaskTimelineEvent,
} from '../../models/opening.model';
import { OpeningsService } from '../../services/openings.service';

type OpeningDetailView = 'DASHBOARD' | 'GANTT' | 'TASKS';
type GanttCellState = 'empty' | 'single' | 'start' | 'middle' | 'end';
type TaskPanelTab = 'BLOCKERS' | 'TIMELINE' | 'DEPENDENCIES' | 'COMMENTS';

@Component({
  selector: 'app-opening-detail',
  standalone: true,
  imports: [
    CommonModule,
    FormsModule,
  ],
  templateUrl: './opening-detail.component.html',
  styleUrls: ['./opening-detail.component.css'],
})
export class OpeningDetailComponent implements OnInit, OnDestroy {
  @ViewChild('ganttScroll') ganttScroll?: ElementRef<HTMLElement>;

  openingId = 0;

  private ganttScrollTimeoutId: number | null = null;

  private ganttScrollAttempt = 0;
  opening: Opening | null = null;
  phases: OpeningPhase[] = [];
  tasks: OpeningTask[] = [];
  dependencies: OpeningTaskDependency[] = [];
  selectedTaskComments: OpeningTaskComment[] = [];
  taskBlockers: OpeningTaskBlocker[] = [];
  selectedTaskTimeline: OpeningTaskTimelineEvent[] = [];
  loadingTimeline = false;

  selectedTask: OpeningTask | null = null;
  activeTaskPanelTab: TaskPanelTab = 'TIMELINE';
  selectedPhaseId: number | 'ALL' = 'ALL';
  private expandedDashboardPhaseIds = new Set<number>();
  activeView: OpeningDetailView = 'GANTT';
  hideCompletedTasksInGantt = true;

  private collapsedGanttPhaseIds = new Set<number>();
  private hasInitializedGanttCollapse = false;

  loading = false;
  savingTask = false;
  savingComment = false;
  savingDependency = false;
  isDependencyFormOpen = false;
  savingBlocker = false;
  resolvingBlockerId: number | null = null;
  blockerResolutionComment = '';
  isBlockerFormOpen = false;

  blockerForm = {
    blocker_type: 'OTHER' as OpeningTaskBlockerType,
    impact_level: 'MEDIUM' as OpeningTaskBlockerImpact,
    reason: '',
    blocking_task_id: null as number | null,
  };

  readonly blockerTypeOptions: Array<{ value: OpeningTaskBlockerType; label: string }> = [
    { value: 'OTHER', label: 'Otro' },
    { value: 'TASK', label: 'Tarea' },
    { value: 'PROVIDER', label: 'Proveedor' },
    { value: 'PAYMENT', label: 'Pago' },
    { value: 'PERMIT', label: 'Permiso' },
    { value: 'DOCUMENT', label: 'Documento' },
    { value: 'DECISION', label: 'Decisión' },
  ];

  readonly blockerImpactOptions: Array<{ value: OpeningTaskBlockerImpact; label: string }> = [
    { value: 'LOW', label: 'Bajo' },
    { value: 'MEDIUM', label: 'Medio' },
    { value: 'HIGH', label: 'Alto' },
    { value: 'CRITICAL', label: 'Crítico' },
  ];


  dependencyForm = {
    depends_on_task_id: null as number | null,
    dependency_type: 'FINISH_TO_START' as OpeningDependencyType,
  };
  errorMessage = '';
  successMessage = '';

  isTaskPanelOpen = false;
  isCreateTaskPanelOpen = false;

  commentDraft = '';

  taskForm = {
    phase_id: null as number | null,
    title: '',
    description: '',
    status: 'NO_INICIADA' as OpeningTaskStatus,
    priority: 'MEDIA' as OpeningTaskPriority,
    planned_start_date: '',
    planned_due_date: '',
    progress_percent: 0,
    sort_order: 0,
    requires_document: false,
    requires_payment: false,
  };

  readonly taskStatusOptions: OpeningTaskStatus[] = [
    'NO_INICIADA',
    'EN_PROCESO',
    'BLOQUEADA',
    'EN_REVISION',
    'COMPLETADA',
    'CANCELADA',
  ];

  readonly taskPriorityOptions: OpeningTaskPriority[] = [
    'BAJA',
    'MEDIA',
    'ALTA',
    'CRITICA',
  ];

  private routeSub?: Subscription;

  constructor(
    private route: ActivatedRoute,
    private router: Router,
    private openingsService: OpeningsService,
  ) {}

  ngOnInit(): void {
    this.routeSub = this.route.paramMap.subscribe((params) => {
      const id = Number(params.get('openingId'));

      if (!id) {
        this.errorMessage = 'Apertura inválida.';
        return;
      }

      this.openingId = id;
      this.loadDashboard();
    });
  }

  ngOnDestroy(): void {
    this.routeSub?.unsubscribe();

    if (this.ganttScrollTimeoutId !== null) {
      window.clearTimeout(this.ganttScrollTimeoutId);
    }
  }

  loadDashboard(): void {
    if (!this.openingId) {
      return;
    }

    this.loading = true;
    this.clearMessages();

    forkJoin({
      openingResponse: this.openingsService.getOpening(this.openingId),
      phasesResponse: this.openingsService.listPhases(this.openingId),
      tasksResponse: this.openingsService.listTasks(this.openingId),
      dependenciesResponse: this.openingsService.listAllDependencies(this.openingId),
      blockersResponse: this.openingsService.listAllBlockers(this.openingId, { status: 'ACTIVE' }),
    }).subscribe({
      next: ({ openingResponse, phasesResponse, tasksResponse, dependenciesResponse, blockersResponse }) => {
        this.opening = openingResponse.item;
        this.phases = phasesResponse.items || [];
        this.tasks = tasksResponse.items || [];
        this.dependencies = dependenciesResponse.items || [];
        this.taskBlockers = blockersResponse.items || [];
        
        this.initializeGanttCollapsedPhases();
        this.initializeDashboardExpandedPhases();

        if (this.selectedTask) {
          const refreshedTask = this.tasks.find((task) => task.id === this.selectedTask?.id);
          this.selectedTask = refreshedTask || null;
        }

        this.loading = false;

        if (this.isActiveView('GANTT')) {
          this.scheduleGanttScrollToToday();
        }
      },
      error: (error) => {
        this.loading = false;
        this.errorMessage = this.resolveErrorMessage(
          error,
          'No se pudo cargar el centro de control de apertura.',
        );
      },
    });
  }

  goBack(): void {
    this.router.navigate(['/aperturas']);
  }

  openCreateTaskPanel(phase?: OpeningPhase): void {
    this.isCreateTaskPanelOpen = true;
    this.resetTaskForm();

    if (phase) {
      this.taskForm.phase_id = phase.id;
      this.taskForm.sort_order = this.getTasksForPhase(phase.id).length * 10 + 10;
    }
  }

  closeCreateTaskPanel(): void {
    this.isCreateTaskPanelOpen = false;
    this.resetTaskForm();
  }

  canCreateTask(): boolean {
    return Boolean(this.taskForm.title.trim() && !this.savingTask);
  }

  createTask(): void {
    if (!this.canCreateTask()) {
      this.errorMessage = 'Captura al menos el título de la tarea.';
      return;
    }

    this.savingTask = true;
    this.clearMessages();

    this.openingsService.createTask(this.openingId, {
      phase_id: this.taskForm.phase_id,
      title: this.taskForm.title.trim(),
      description: this.taskForm.description.trim() || null,
      status: this.taskForm.status,
      priority: this.taskForm.priority,
      planned_start_date: this.taskForm.planned_start_date || null,
      planned_due_date: this.taskForm.planned_due_date || null,
      progress_percent: this.taskForm.progress_percent || 0,
      sort_order: this.taskForm.sort_order || 0,
      requires_document: this.taskForm.requires_document,
      requires_payment: this.taskForm.requires_payment,
    }).subscribe({
      next: (response) => {
        this.savingTask = false;
        this.successMessage = response.message || 'Tarea creada.';
        this.closeCreateTaskPanel();
        this.loadDashboard();

        if (response.item) {
          this.selectTask(response.item);
        }
      },
      error: (error) => {
        this.savingTask = false;
        this.errorMessage = this.resolveErrorMessage(
          error,
          'No se pudo crear la tarea.',
        );
      },
    });
  }

  selectTask(task: OpeningTask): void {
    this.selectedTask = task;
    this.isTaskPanelOpen = true;
    this.setDefaultTaskPanelTab(task);
    this.commentDraft = '';
    this.loadSelectedTaskComments();
    this.loadTaskTimeline(task.id);
  }

  closeTaskPanel(): void {
    this.selectedTask = null;
    this.selectedTaskComments = [];
    this.selectedTaskTimeline = [];
    this.commentDraft = '';
    this.loadingTimeline = false;
    this.closeBlockerForm();
    this.cancelResolveBlocker();
    this.isTaskPanelOpen = false;
  }

  loadSelectedTaskComments(): void {
    if (!this.selectedTask) {
      this.selectedTaskComments = [];
      return;
    }

    this.openingsService
      .listTaskComments(this.openingId, this.selectedTask.id)
      .subscribe({
        next: (response) => {
          this.selectedTaskComments = response.items || [];
        },
        error: () => {
          this.selectedTaskComments = [];
        },
      });
  }

  private loadTaskTimeline(taskId: number): void {
    this.loadingTimeline = true;
    this.selectedTaskTimeline = [];

    this.openingsService.listTaskTimeline(this.openingId, taskId).subscribe({
      next: (response) => {
        this.loadingTimeline = false;
        this.selectedTaskTimeline = response.items || [];
      },
      error: (error) => {
        this.loadingTimeline = false;
        this.selectedTaskTimeline = [];
        this.errorMessage = this.resolveErrorMessage(
          error,
          'No se pudo cargar la bitácora de la tarea.',
        );
      },
    });
    }

  canAddComment(): boolean {
    return Boolean(this.selectedTask && this.commentDraft.trim() && !this.savingComment);
  }

  addComment(): void {
    if (!this.selectedTask || !this.canAddComment()) {
      return;
    }

    this.savingComment = true;
    this.clearMessages();

    this.openingsService
      .createTaskComment(this.openingId, this.selectedTask.id, {
        comment: this.commentDraft.trim(),
      })
      .subscribe({
        next: (response) => {
          this.savingComment = false;
          this.commentDraft = '';
          this.successMessage = response.message || 'Comentario agregado.';
          this.loadSelectedTaskComments();
        },
        error: (error) => {
          this.savingComment = false;
          this.errorMessage = this.resolveErrorMessage(
            error,
            'No se pudo agregar el comentario.',
          );
        },
      });
  }

  updateSelectedTaskStatus(status: OpeningTaskStatus): void {
    if (!this.selectedTask) {
      return;
    }

    this.savingTask = true;
    this.clearMessages();

    this.openingsService
      .updateTask(this.openingId, this.selectedTask.id, { status })
      .subscribe({
        next: (response) => {
          this.savingTask = false;
          this.successMessage = response.message || 'Tarea actualizada.';
          this.selectedTask = response.item;
          this.loadDashboard();
        },
        error: (error) => {
          this.savingTask = false;
          this.errorMessage = this.resolveErrorMessage(
            error,
            'No se pudo actualizar la tarea.',
          );
        },
      });
  }

  setPhaseFilter(phaseId: number | 'ALL'): void {
    this.selectedPhaseId = phaseId;
  }

  getVisiblePhases(): OpeningPhase[] {
    return [...this.phases].sort((a, b) => {
      return (a.sort_order || 0) - (b.sort_order || 0) || a.id - b.id;
    });
  }

  getVisibleTasks(): OpeningTask[] {
    const tasks = this.tasks.filter((task) => {
      if (this.selectedPhaseId === 'ALL') {
        return true;
      }

      return task.phase_id === this.selectedPhaseId;
    });

    return [...tasks].sort((a, b) => {
      return (a.phase_id || 0) - (b.phase_id || 0) ||
        (a.sort_order || 0) - (b.sort_order || 0) ||
        a.id - b.id;
    });
  }

  getTasksForPhase(phaseId: number): OpeningTask[] {
    return this.tasks
      .filter((task) => task.phase_id === phaseId)
      .sort((a, b) => (a.sort_order || 0) - (b.sort_order || 0) || a.id - b.id);
  }

  getTasksWithoutPhase(): OpeningTask[] {
    return this.tasks
      .filter((task) => !task.phase_id)
      .sort((a, b) => (a.sort_order || 0) - (b.sort_order || 0) || a.id - b.id);
  }

  getTaskDependencies(task: OpeningTask | null): OpeningTaskDependency[] {
    if (!task) {
      return [];
    }

    return this.dependencies.filter((dependency) => dependency.task_id === task.id);
  }

  getTaskBlockers(task: OpeningTask | null): OpeningTaskBlocker[] {
    if (!task) {
      return [];
    }

    return this.taskBlockers.filter((blocker) => {
      return blocker.blocked_task_id === task.id && blocker.status === 'ACTIVE';
    });
  }

  getTaskCardDomId(task: OpeningTask | null): string {
    return task ? `opening-task-card-${task.id}` : '';
  }

  getTimelineEventTone(event: OpeningTaskTimelineEvent): string {
    const eventType = String(event.event_type || '').toUpperCase();

    if (eventType === 'BLOCKER') {
      return 'danger';
    }

    if (eventType === 'DEPENDENCY') {
      return 'warning';
    }

    if (eventType === 'COMMENT') {
      return 'neutral';
    }

    return 'primary';
  }

  getTimelineEventLabel(event: OpeningTaskTimelineEvent): string {
    const eventType = String(event.event_type || '').toUpperCase();

    const labels: Record<string, string> = {
      AUDIT: 'Sistema',
      COMMENT: 'Comentario',
      BLOCKER: 'Bloqueo',
      DEPENDENCY: 'Dependencia',
    };

    return labels[eventType] || 'Evento';
  }

  getTimelineActorLabel(event: OpeningTaskTimelineEvent): string {
    return event.actor?.username || 'Sistema';
  }

setTaskPanelTab(tab: TaskPanelTab): void {
  this.activeTaskPanelTab = tab;
}

isTaskPanelTab(tab: TaskPanelTab): boolean {
  return this.activeTaskPanelTab === tab;
}

getTaskPanelTabCount(tab: TaskPanelTab): number {
  if (tab === 'BLOCKERS') {
    return this.getTaskBlockers(this.selectedTask).length;
  }

  if (tab === 'TIMELINE') {
    return this.selectedTaskTimeline.length;
  }

  if (tab === 'DEPENDENCIES') {
    return this.getTaskDependencies(this.selectedTask).length;
  }

  if (tab === 'COMMENTS') {
    return this.selectedTaskComments.length;
  }

  return 0;
}

private setDefaultTaskPanelTab(task: OpeningTask): void {
  if (this.hasActiveBlockers(task)) {
    this.activeTaskPanelTab = 'BLOCKERS';
    return;
  }

  this.activeTaskPanelTab = 'TIMELINE';
}  

  openBlockerForm(): void {
    if (!this.selectedTask) {
      return;
    }

    this.isBlockerFormOpen = true;
    this.resolvingBlockerId = null;
    this.blockerResolutionComment = '';
    this.resetBlockerForm();
    this.clearMessages();
  }

  closeBlockerForm(): void {
    this.isBlockerFormOpen = false;
    this.resetBlockerForm();
  }

  isTaskBlockerFormType(): boolean {
    return this.blockerForm.blocker_type === 'TASK';
  }

  canCreateBlocker(): boolean {
    if (!this.selectedTask || this.savingBlocker) {
      return false;
    }

    if (!this.blockerForm.reason.trim()) {
      return false;
    }

    if (this.isTaskBlockerFormType() && !this.blockerForm.blocking_task_id) {
      return false;
    }

    return true;
  }

  getAvailableBlockingTasks(): OpeningTask[] {
    if (!this.selectedTask) {
      return [];
    }

    return this.tasks
      .filter((task) => task.id !== this.selectedTask?.id)
      .sort((a, b) => {
        return (a.phase_id || 0) - (b.phase_id || 0) ||
          (a.sort_order || 0) - (b.sort_order || 0) ||
          a.id - b.id;
      });
  }

  createBlocker(): void {
    if (!this.selectedTask || !this.canCreateBlocker()) {
      return;
    }

    this.savingBlocker = true;
    this.clearMessages();

    this.openingsService.createTaskBlocker(this.openingId, this.selectedTask.id, {
      blocker_type: this.blockerForm.blocker_type,
      impact_level: this.blockerForm.impact_level,
      reason: this.blockerForm.reason.trim(),
      blocking_task_id: this.isTaskBlockerFormType()
        ? this.blockerForm.blocking_task_id
        : null,
    }).subscribe({
      next: (response) => {
        this.savingBlocker = false;
        this.taskBlockers = [...this.taskBlockers, response.item];
        if (this.selectedTask) {
          this.loadTaskTimeline(this.selectedTask.id);
        }

        this.activeTaskPanelTab = 'BLOCKERS';
        this.successMessage = response.message || 'Bloqueo creado.';
        this.closeBlockerForm();
      },
      error: (error) => {
        this.savingBlocker = false;
        this.errorMessage = this.resolveErrorMessage(
          error,
          'No se pudo crear el bloqueo.',
        );
      },
    });
  }

  private resetBlockerForm(): void {
    this.blockerForm = {
      blocker_type: 'OTHER',
      impact_level: 'MEDIUM',
      reason: '',
      blocking_task_id: null,
    };
  }

  private scrollToTaskCard(taskId: number): void {
    window.setTimeout(() => {
      const element = document.getElementById(`opening-task-card-${taskId}`);

      if (!element) {
        return;
      }

      element.scrollIntoView({
        behavior: 'smooth',
        block: 'center',
        inline: 'nearest',
      });
    }, 220);
  }

  resolveBlocker(blockerId: number): void {
    if (!this.selectedTask || this.savingBlocker || !this.canConfirmResolveBlocker()) {
      return;
    }

    this.savingBlocker = true;
    this.clearMessages();

    this.openingsService.resolveTaskBlocker(this.openingId, blockerId, {
      resolution_comment: this.blockerResolutionComment.trim(),
    }).subscribe({
      next: (response) => {
        this.savingBlocker = false;

        this.taskBlockers = this.taskBlockers.filter((blocker) => {
          return blocker.id !== blockerId;
        });

        if (this.selectedTask) {
          this.loadTaskTimeline(this.selectedTask.id);
        }

        this.activeTaskPanelTab = 'TIMELINE';

        this.resolvingBlockerId = null;
        this.blockerResolutionComment = '';
        this.successMessage = response.message || 'Bloqueo resuelto.';
      },
      error: (error) => {
        this.savingBlocker = false;
        this.errorMessage = this.resolveErrorMessage(
          error,
          'No se pudo resolver el bloqueo.',
        );
      },
    });
  }

  openResolveBlockerForm(blockerId: number): void {
    this.resolvingBlockerId = blockerId;
    this.blockerResolutionComment = '';
    this.clearMessages();
  }

  cancelResolveBlocker(): void {
    this.resolvingBlockerId = null;
    this.blockerResolutionComment = '';
  }

  canConfirmResolveBlocker(): boolean {
    return Boolean(
      this.selectedTask &&
      this.resolvingBlockerId &&
      this.blockerResolutionComment.trim() &&
      !this.savingBlocker,
    );
  }

  hasActiveBlockers(task: OpeningTask | null): boolean {
    return this.getTaskBlockers(task).length > 0;
  }

  getActiveBlockersCountForTask(task: OpeningTask | null): number {
    return this.getTaskBlockers(task).length;
  }

  getBlockerTypeLabel(type: OpeningTaskBlockerType | string | null | undefined): string {
    const labels: Record<string, string> = {
      TASK: 'Tarea',
      PROVIDER: 'Proveedor',
      PAYMENT: 'Pago',
      PERMIT: 'Permiso',
      DOCUMENT: 'Documento',
      DECISION: 'Decisión',
      OTHER: 'Otro',
    };

    return labels[String(type || '')] || String(type || 'Otro');
  }

  getBlockerImpactLabel(impact: OpeningTaskBlockerImpact | string | null | undefined): string {
    const labels: Record<string, string> = {
      LOW: 'Bajo',
      MEDIUM: 'Medio',
      HIGH: 'Alto',
      CRITICAL: 'Crítico',
    };

    return labels[String(impact || '')] || String(impact || 'Medio');
  }

  getBlockerImpactTone(impact: OpeningTaskBlockerImpact | string | null | undefined): string {
    const tones: Record<string, string> = {
      LOW: 'neutral',
      MEDIUM: 'warning',
      HIGH: 'danger',
      CRITICAL: 'critical',
    };

    return tones[String(impact || '')] || 'warning';
  }

  openDependencyForm(): void {
    this.isDependencyFormOpen = true;
    this.resetDependencyForm();
  }

  closeDependencyForm(): void {
    this.isDependencyFormOpen = false;
    this.resetDependencyForm();
  }

  canCreateDependency(): boolean {
    return Boolean(
      this.selectedTask &&
      this.dependencyForm.depends_on_task_id &&
      !this.savingDependency &&
      !this.isDependencyAlreadyRegistered(this.dependencyForm.depends_on_task_id),
    );
  }

  createDependency(): void {
    if (!this.selectedTask || !this.canCreateDependency()) {
      return;
    }

    const dependsOnTaskId = this.dependencyForm.depends_on_task_id;

    if (!dependsOnTaskId) {
      return;
    }

    this.savingDependency = true;
    this.clearMessages();

    this.openingsService.createTaskDependency(this.openingId, this.selectedTask.id, {
      depends_on_task_id: dependsOnTaskId,
      dependency_type: this.dependencyForm.dependency_type,
    }).subscribe({
      next: (response) => {
        this.savingDependency = false;
        this.dependencies = [...this.dependencies, response.item];
        this.successMessage = response.message || 'Dependencia agregada.';
        this.closeDependencyForm();
      },
      error: (error) => {
        this.savingDependency = false;
        this.errorMessage = error?.error?.error || 'No se pudo agregar la dependencia.';
      },
    });
  }

  deleteDependency(dependencyId: number): void {
    if (!this.selectedTask || this.savingDependency) {
      return;
    }

    this.savingDependency = true;
    this.clearMessages();

    this.openingsService.deleteTaskDependency(this.openingId, dependencyId).subscribe({
      next: (response) => {
        this.savingDependency = false;
        this.dependencies = this.dependencies.filter((dependency) => dependency.id !== dependencyId);
        this.successMessage = response.message || 'Dependencia eliminada.';
      },
      error: (error) => {
        this.savingDependency = false;
        this.errorMessage = error?.error?.error || 'No se pudo eliminar la dependencia.';
      },
    });
  }

  getAvailableDependencyTasks(): OpeningTask[] {
    if (!this.selectedTask) {
      return [];
    }

    return this.tasks
      .filter((task) => task.id !== this.selectedTask?.id)
      .filter((task) => !this.isDependencyAlreadyRegistered(task.id))
      .sort((a, b) => {
        return (a.phase_id || 0) - (b.phase_id || 0) ||
          (a.sort_order || 0) - (b.sort_order || 0) ||
          a.id - b.id;
      });
  }

  isDependencyAlreadyRegistered(taskId: number | null): boolean {
    if (!this.selectedTask || !taskId) {
      return false;
    }

    return this.getTaskDependencies(this.selectedTask)
      .some((dependency) => dependency.depends_on_task_id === taskId);
  }

  getDependencyTypeLabel(type: OpeningDependencyType): string {
    const labels: Record<OpeningDependencyType, string> = {
      BLOCKER: 'Bloqueo',
      FINISH_TO_START: 'Finaliza antes de iniciar',
      START_TO_START: 'Inician juntas',
      FINISH_TO_FINISH: 'Finalizan juntas',
    };

    return labels[type] || type;
  }

  private resetDependencyForm(): void {
    this.dependencyForm = {
      depends_on_task_id: null,
      dependency_type: 'FINISH_TO_START',
    };
  }

  getBlockedTasksCount(): number {
    return this.getBlockedTasks().length;
  }
  
  getBlockedTasks(): OpeningTask[] {
    return this.tasks.filter((task) => {
      return task.status === 'BLOQUEADA' || this.hasActiveBlockers(task);
    });
  }

  focusFirstBlockedTask(): void {
    const blockedTask = this.getBlockedTasks()[0];

    if (!blockedTask) {
      this.successMessage = '';
      this.errorMessage = 'No hay tareas bloqueadas por revisar.';
      return;
    }

    this.setActiveView('DASHBOARD');
    this.expandDashboardPhaseForTask(blockedTask);
    this.selectTask(blockedTask);
    this.scrollToTaskCard(blockedTask.id);
  }

  getAtRiskTasksCount(): number {
    return this.tasks.filter((task) => {
      return task.status !== 'COMPLETADA' && this.isTaskOverdue(task);
    }).length;
  }

  getCompletedTasksCount(): number {
    return this.tasks.filter((task) => task.status === 'COMPLETADA').length;
  }

  getActiveTasksCount(): number {
    return this.tasks.filter((task) =>
      ['NO_INICIADA', 'EN_PROCESO', 'BLOQUEADA', 'EN_REVISION'].includes(task.status),
    ).length;
  }

  getGeneralProgress(): number {
    if (this.tasks.length === 0) {
      return 0;
    }

    const totalProgress = this.tasks.reduce((total, task) => {
      return total + Number(task.progress_percent || 0);
    }, 0);

    return Math.round(totalProgress / this.tasks.length);
  }

  getPhaseProgress(phase: OpeningPhase): number {
    const phaseTasks = this.getTasksForPhase(phase.id);

    if (phaseTasks.length === 0) {
      return Number(phase.progress_percent || 0);
    }

    const totalProgress = phaseTasks.reduce((total, task) => {
      return total + Number(task.progress_percent || 0);
    }, 0);

    return Math.round(totalProgress / phaseTasks.length);
  }

  getPhaseCompletedTasks(phase: OpeningPhase): number {
    return this.getTasksForPhase(phase.id)
      .filter((task) => task.status === 'COMPLETADA')
      .length;
  }

  getDaysRemaining(): number | null {
    if (!this.opening?.target_opening_date) {
      return null;
    }

    const today = new Date();
    const target = new Date(`${this.opening.target_opening_date}T00:00:00`);
    const todayStart = new Date(today.getFullYear(), today.getMonth(), today.getDate());
    const diffMs = target.getTime() - todayStart.getTime();

    return Math.ceil(diffMs / (1000 * 60 * 60 * 24));
  }

  getDaysRemainingLabel(): string {
    const days = this.getDaysRemaining();

    if (days === null) {
      return 'Sin fecha objetivo';
    }

    if (days < 0) {
      return `${Math.abs(days)} días de atraso`;
    }

    if (days === 0) {
      return 'Apertura hoy';
    }

    return `${days} días restantes`;
  }

  getDaysRemainingTone(): string {
    const days = this.getDaysRemaining();

    if (days === null) {
      return 'neutral';
    }

    if (days < 0) {
      return 'danger';
    }

    if (days <= 7) {
      return 'warning';
    }

    return 'success';
  }

  isTaskOverdue(task: OpeningTask): boolean {
    if (!task.planned_due_date || task.status === 'COMPLETADA' || task.status === 'CANCELADA') {
      return false;
    }

    const today = new Date();
    const due = new Date(`${task.planned_due_date}T00:00:00`);
    const todayStart = new Date(today.getFullYear(), today.getMonth(), today.getDate());

    return due.getTime() < todayStart.getTime();
  }

  getOpeningStatusLabel(): string {
    return this.getStatusLabel(this.opening?.status);
  }

  getStatusLabel(status: string | null | undefined): string {
    const labels: Record<string, string> = {
      BORRADOR: 'Borrador',
      PLANEADA: 'Planeada',
      EN_EJECUCION: 'En ejecución',
      EN_RIESGO: 'En riesgo',
      PAUSADA: 'Pausada',
      ABIERTA: 'Abierta',
      CANCELADA: 'Cancelada',
      CERRADA: 'Cerrada',
      NO_INICIADA: 'No iniciada',
      EN_PROCESO: 'En proceso',
      BLOQUEADA: 'Bloqueada',
      EN_REVISION: 'En revisión',
      COMPLETADA: 'Completada',
    };

    return labels[String(status || '')] || String(status || 'Sin estado');
  }

  getPriorityLabel(priority: string | null | undefined): string {
    const labels: Record<string, string> = {
      BAJA: 'Baja',
      MEDIA: 'Media',
      ALTA: 'Alta',
      CRITICA: 'Crítica',
    };

    return labels[String(priority || '')] || String(priority || 'Sin prioridad');
  }

  getStatusTone(status: string | null | undefined): string {
    const tones: Record<string, string> = {
      BORRADOR: 'draft',
      PLANEADA: 'planned',
      EN_EJECUCION: 'progress',
      EN_RIESGO: 'risk',
      PAUSADA: 'paused',
      ABIERTA: 'opened',
      CANCELADA: 'cancelled',
      CERRADA: 'closed',
      NO_INICIADA: 'draft',
      EN_PROCESO: 'progress',
      BLOQUEADA: 'risk',
      EN_REVISION: 'review',
      COMPLETADA: 'opened',
    };

    return tones[String(status || '')] || 'draft';
  }

  getPriorityTone(priority: string | null | undefined): string {
    const tones: Record<string, string> = {
      BAJA: 'low',
      MEDIA: 'medium',
      ALTA: 'high',
      CRITICA: 'critical',
    };

    return tones[String(priority || '')] || 'medium';
  }

  getDateLabel(value: string | null | undefined, emptyLabel = 'Sin fecha'): string {
    if (!value) {
      return emptyLabel;
    }

    const date = new Date(value.includes('T') ? value : `${value}T00:00:00`);

    if (Number.isNaN(date.getTime())) {
      return value;
    }

    return new Intl.DateTimeFormat('es-MX', {
      dateStyle: 'medium',
      timeZone: 'America/Tijuana',
    }).format(date);
  }

  getDateTimeLabel(value: string | null | undefined): string {
    if (!value) {
      return 'Sin fecha';
    }

    const date = new Date(value);

    if (Number.isNaN(date.getTime())) {
      return value;
    }

    return new Intl.DateTimeFormat('es-MX', {
      dateStyle: 'medium',
      timeStyle: 'short',
      timeZone: 'America/Tijuana',
    }).format(date);
  }

  getMoneyLabel(value: number | null | undefined, currency = 'MXN'): string {
    return new Intl.NumberFormat('es-MX', {
      style: 'currency',
      currency: currency || 'MXN',
      maximumFractionDigits: 0,
    }).format(Number(value || 0));
  }

  getSucursalName(): string {
    return this.opening?.sucursal?.sucursal || `Sucursal ${this.opening?.sucursal_id || ''}`;
  }

  getOpeningLocation(): string {
    const municipio = this.opening?.sucursal?.municipio;
    const estado = this.opening?.sucursal?.estado;

    return [municipio, estado].filter(Boolean).join(', ') || this.getSucursalName();
  }

  getOwnerLabel(): string {
    return this.opening?.general_owner_user?.username || 'Sin responsable general';
  }

  getPhaseNameById(phaseId: number | null): string {
    if (!phaseId) {
      return 'Sin fase';
    }

    return this.phases.find((phase) => phase.id === phaseId)?.name || 'Sin fase';
  }

  getTaskOwnerLabel(task: OpeningTask | null): string {
    if (!task) {
      return 'Sin responsable';
    }

    return task.owner_user?.username ||
      task.owner_department?.nombre ||
      'Sin responsable';
  }

  getTaskDueTone(task: OpeningTask): string {
    if (this.isTaskOverdue(task)) {
      return 'danger';
    }

    if (!task.planned_due_date) {
      return 'neutral';
    }

    return 'success';
  }

  getOpeningInitial(): string {
    const source = this.opening?.opening_key || this.opening?.name || 'A';

    return source.trim().charAt(0).toUpperCase() || 'A';
  }

  setActiveView(view: OpeningDetailView): void {
    this.activeView = view;

    if (view === 'GANTT') {
      this.scheduleGanttScrollToToday();
    }
  }

  isActiveView(view: OpeningDetailView): boolean {
    return this.activeView === view;
  }

  getGanttDays(): string[] {
    const start = this.getGanttRangeStart();
    const end = this.getGanttRangeEnd(start);
    const days: string[] = [];

    const cursor = new Date(start);

    while (cursor.getTime() <= end.getTime()) {
      days.push(this.toIsoDate(cursor));
      cursor.setDate(cursor.getDate() + 1);
    }

    return days;
  }

  scheduleGanttScrollToToday(): void {
    if (this.ganttScrollTimeoutId !== null) {
      window.clearTimeout(this.ganttScrollTimeoutId);
    }

    this.ganttScrollAttempt = 0;
    this.tryScrollGanttToToday();
  }

  private tryScrollGanttToToday(): void {
    this.ganttScrollTimeoutId = window.setTimeout(() => {
      const didScroll = this.scrollGanttToToday();

      if (!didScroll && this.ganttScrollAttempt < 12) {
        this.ganttScrollAttempt += 1;
        this.tryScrollGanttToToday();
      }
    }, 120);
  }

  private scrollGanttToToday(): boolean {
    const scrollElement = this.ganttScroll?.nativeElement;

    if (!scrollElement) {
      return false;
    }

    const todayIso = this.toIsoDate(new Date());
    const todayHeader = scrollElement.querySelector<HTMLElement>(
      `[data-gantt-day="${todayIso}"]`,
    );

    const labelHeader = scrollElement.querySelector<HTMLElement>('.gantt-label-header');

    if (!todayHeader) {
      return false;
    }

    if (scrollElement.scrollWidth <= scrollElement.clientWidth) {
      return false;
    }

    const labelWidth = labelHeader?.offsetWidth || 260;
    const dayWidth = todayHeader.offsetWidth || 58;
    const contextDaysBeforeToday = 4;

    const targetLeft = Math.max(
      todayHeader.offsetLeft - labelWidth - dayWidth * contextDaysBeforeToday,
      0,
    );

    scrollElement.scrollTo({
      left: targetLeft,
      behavior: 'smooth',
    });

    return true;
  }

  private expandDashboardPhaseForTask(task: OpeningTask): void {
    if (!task.phase_id) {
      return;
    }

    this.expandedDashboardPhaseIds.add(task.phase_id);
  }

  getGanttDayNumber(dayIso: string): string {
    const date = this.parseDateOnly(dayIso);

    if (!date) {
      return '';
    }

    return new Intl.DateTimeFormat('es-MX', {
      day: '2-digit',
      timeZone: 'America/Tijuana',
    }).format(date);
  }

  getGanttWeekday(dayIso: string): string {
    const date = this.parseDateOnly(dayIso);

    if (!date) {
      return '';
    }

    return new Intl.DateTimeFormat('es-MX', {
      weekday: 'short',
      timeZone: 'America/Tijuana',
    }).format(date).replace('.', '');
  }

  getGanttMonth(dayIso: string): string {
    const date = this.parseDateOnly(dayIso);

    if (!date) {
      return '';
    }

    return new Intl.DateTimeFormat('es-MX', {
      month: 'short',
      timeZone: 'America/Tijuana',
    }).format(date).replace('.', '');
  }

  isGanttToday(dayIso: string): boolean {
    return dayIso === this.toIsoDate(new Date());
  }

  getGanttPhaseCellState(phase: OpeningPhase, dayIso: string): GanttCellState {
    return this.getGanttCellState(
      this.getPhaseGanttStart(phase),
      this.getPhaseGanttEnd(phase),
      dayIso,
    );
  }

  getGanttTaskCellState(task: OpeningTask, dayIso: string): GanttCellState {
    return this.getGanttCellState(
      this.getTaskGanttStart(task),
      this.getTaskGanttEnd(task),
      dayIso,
    );
  }

  isGanttPhaseCellActive(phase: OpeningPhase, dayIso: string): boolean {
    return this.getGanttPhaseCellState(phase, dayIso) !== 'empty';
  }

  isGanttTaskCellActive(task: OpeningTask, dayIso: string): boolean {
    return this.getGanttTaskCellState(task, dayIso) !== 'empty';
  }

  isGanttPhaseCellStart(phase: OpeningPhase, dayIso: string): boolean {
    const state = this.getGanttPhaseCellState(phase, dayIso);

    return state === 'start' || state === 'single';
  }

  isGanttPhaseCellEnd(phase: OpeningPhase, dayIso: string): boolean {
    const state = this.getGanttPhaseCellState(phase, dayIso);

    return state === 'end' || state === 'single';
  }

  isGanttTaskCellStart(task: OpeningTask, dayIso: string): boolean {
    const state = this.getGanttTaskCellState(task, dayIso);

    return state === 'start' || state === 'single';
  }

  isGanttTaskCellEnd(task: OpeningTask, dayIso: string): boolean {
    const state = this.getGanttTaskCellState(task, dayIso);

    return state === 'end' || state === 'single';
  }

  getGanttPhaseLabelForCell(phase: OpeningPhase, dayIso: string): string {
    if (!this.isGanttPhaseCellStart(phase, dayIso)) {
      return '';
    }

    return phase.name;
  }

  getGanttTaskLabelForCell(task: OpeningTask, dayIso: string): string {
    if (!this.isGanttTaskCellStart(task, dayIso)) {
      return '';
    }

    return task.title;
  }

  getTasksWithoutGanttDates(): OpeningTask[] {
    return this.tasks.filter((task) => {
      return !this.getTaskGanttStart(task) || !this.getTaskGanttEnd(task);
    });
  }

  getGanttVisibleRangeLabel(): string {
    const days = this.getGanttDays();

    if (days.length === 0) {
      return 'Sin rango';
    }

    const first = this.getDateLabel(days[0]);
    const last = this.getDateLabel(days[days.length - 1]);

    return `${first} → ${last}`;
  }

  private getGanttRangeStart(): Date {
    const candidates = [
      this.opening?.planned_start_date,
      ...this.phases.map((phase) => phase.planned_start_date),
      ...this.tasks.map((task) => task.planned_start_date || task.planned_due_date),
    ]
      .map((value) => this.parseDateOnly(value))
      .filter((value): value is Date => Boolean(value));

    if (candidates.length === 0) {
      const today = new Date();
      return new Date(today.getFullYear(), today.getMonth(), today.getDate());
    }

    const minTime = Math.min(...candidates.map((date) => date.getTime()));
    const start = new Date(minTime);
    start.setDate(start.getDate() - 1);

    return start;
  }

  private getGanttRangeEnd(start: Date): Date {
    const candidates = [
      this.opening?.target_opening_date,
      ...this.phases.map((phase) => phase.planned_end_date || phase.planned_start_date),
      ...this.tasks.map((task) => task.planned_due_date || task.planned_start_date),
    ]
      .map((value) => this.parseDateOnly(value))
      .filter((value): value is Date => Boolean(value));

    const minimumEnd = new Date(start);
    minimumEnd.setDate(minimumEnd.getDate() + 21);

    if (candidates.length === 0) {
      return minimumEnd;
    }

    const maxTime = Math.max(...candidates.map((date) => date.getTime()));
    const detectedEnd = new Date(maxTime);
    detectedEnd.setDate(detectedEnd.getDate() + 2);

    const end = detectedEnd.getTime() < minimumEnd.getTime()
      ? minimumEnd
      : detectedEnd;

    const maxAllowedEnd = new Date(start);
    maxAllowedEnd.setDate(maxAllowedEnd.getDate() + 120);

    if (end.getTime() > maxAllowedEnd.getTime()) {
      return maxAllowedEnd;
    }

    return end;
  }

  private getPhaseGanttStart(phase: OpeningPhase): string | null {
    if (phase.planned_start_date) {
      return phase.planned_start_date;
    }

    const tasks = this.getTasksForPhase(phase.id);
    const starts = tasks
      .map((task) => this.getTaskGanttStart(task))
      .filter((value): value is string => Boolean(value));

    return this.getMinIsoDate(starts);
  }

  private getPhaseGanttEnd(phase: OpeningPhase): string | null {
    if (phase.planned_end_date) {
      return phase.planned_end_date;
    }

    const tasks = this.getTasksForPhase(phase.id);
    const ends = tasks
      .map((task) => this.getTaskGanttEnd(task))
      .filter((value): value is string => Boolean(value));

    return this.getMaxIsoDate(ends) || this.getPhaseGanttStart(phase);
  }

  private getTaskGanttStart(task: OpeningTask): string | null {
    return task.planned_start_date || task.planned_due_date || null;
  }

  private getTaskGanttEnd(task: OpeningTask): string | null {
    return task.planned_due_date || task.planned_start_date || null;
  }

  private getGanttCellState(
    startIso: string | null,
    endIso: string | null,
    dayIso: string,
  ): GanttCellState {
    if (!startIso || !endIso) {
      return 'empty';
    }

    const start = startIso <= endIso ? startIso : endIso;
    const end = startIso <= endIso ? endIso : startIso;

    if (dayIso < start || dayIso > end) {
      return 'empty';
    }

    if (start === end && dayIso === start) {
      return 'single';
    }

    if (dayIso === start) {
      return 'start';
    }

    if (dayIso === end) {
      return 'end';
    }

    return 'middle';
  }

  private getMinIsoDate(values: string[]): string | null {
    if (values.length === 0) {
      return null;
    }

    return [...values].sort()[0];
  }

  private getMaxIsoDate(values: string[]): string | null {
    if (values.length === 0) {
      return null;
    }

    return [...values].sort().reverse()[0];
  }

  private parseDateOnly(value: string | null | undefined): Date | null {
    if (!value) {
      return null;
    }

    const normalized = value.includes('T') ? value.split('T')[0] : value;
    const date = new Date(`${normalized}T00:00:00`);

    if (Number.isNaN(date.getTime())) {
      return null;
    }

    return date;
  }

  private toIsoDate(date: Date): string {
    const year = date.getFullYear();
    const month = String(date.getMonth() + 1).padStart(2, '0');
    const day = String(date.getDate()).padStart(2, '0');

    return `${year}-${month}-${day}`;
  }

  isGanttPhaseCollapsed(phase: OpeningPhase): boolean {
    return this.collapsedGanttPhaseIds.has(phase.id);
  }

  toggleGanttPhase(phase: OpeningPhase): void {
    if (this.collapsedGanttPhaseIds.has(phase.id)) {
      this.collapsedGanttPhaseIds.delete(phase.id);
      return;
    }

    this.collapsedGanttPhaseIds.add(phase.id);
  }

  expandAllGanttPhases(): void {
    this.collapsedGanttPhaseIds.clear();
  }

  collapseAllGanttPhases(): void {
    this.collapsedGanttPhaseIds = new Set(
      this.getVisiblePhases().map((phase) => phase.id),
    );
  }

  toggleCompletedTasksInGantt(): void {
    this.hideCompletedTasksInGantt = !this.hideCompletedTasksInGantt;
  }

  getGanttTasksForPhase(phase: OpeningPhase): OpeningTask[] {
    if (this.isGanttPhaseCollapsed(phase)) {
      return [];
    }

    const tasks = this.getTasksForPhase(phase.id);

    if (!this.hideCompletedTasksInGantt) {
      return tasks;
    }

    return tasks.filter((task) => task.status !== 'COMPLETADA');
  }

  getCompletedTasksForPhaseCount(phase: OpeningPhase): number {
    return this.getTasksForPhase(phase.id)
      .filter((task) => task.status === 'COMPLETADA')
      .length;
  }

  getHiddenCompletedTasksForPhaseCount(phase: OpeningPhase): number {
    if (!this.hideCompletedTasksInGantt) {
      return 0;
    }

    return this.getCompletedTasksForPhaseCount(phase);
  }

  getGanttPhaseVisibleTasksCount(phase: OpeningPhase): number {
    return this.getGanttTasksForPhase(phase).length;
  }

  getGanttPhaseToggleLabel(phase: OpeningPhase): string {
    return this.isGanttPhaseCollapsed(phase) ? 'Expandir' : 'Contraer';
  }

  private initializeGanttCollapsedPhases(): void {
    if (this.hasInitializedGanttCollapse) {
      return;
    }

    this.collapsedGanttPhaseIds = new Set(
      this.getVisiblePhases().map((phase) => phase.id),
    );

    this.hasInitializedGanttCollapse = true;
  }

  isDashboardPhaseExpanded(phase: OpeningPhase): boolean {
    return this.expandedDashboardPhaseIds.has(phase.id);
  }

  toggleDashboardPhase(phase: OpeningPhase): void {
    if (this.expandedDashboardPhaseIds.has(phase.id)) {
      this.expandedDashboardPhaseIds.delete(phase.id);
      return;
    }

    this.expandedDashboardPhaseIds.add(phase.id);
  }

  expandAllDashboardPhases(): void {
    this.expandedDashboardPhaseIds = new Set(
      this.getVisiblePhases().map((phase) => phase.id),
    );
  }

  collapseAllDashboardPhases(): void {
    this.expandedDashboardPhaseIds.clear();
  }

  getDashboardPhaseToggleLabel(phase: OpeningPhase): string {
    return this.isDashboardPhaseExpanded(phase) ? 'Ocultar tareas' : 'Ver tareas';
  }

  private initializeDashboardExpandedPhases(): void {
    // Intencionalmente vacío:
    // el Dashboard debe iniciar con todas las fases contraídas.
    // El usuario expande manualmente la fase que quiera revisar.
  }
  trackByPhaseId(_index: number, phase: OpeningPhase): number {
    return phase.id;
  }

  trackByTaskId(_index: number, task: OpeningTask): number {
    return task.id;
  }

  trackByDependencyId(_index: number, dependency: OpeningTaskDependency): number {
    return dependency.id;
  }

  trackByBlockerId(_index: number, blocker: OpeningTaskBlocker): number {
    return blocker.id;
  }  

  trackByCommentId(_index: number, comment: OpeningTaskComment): number {
    return comment.id;
  }

  trackByTimelineEventId(_index: number, event: OpeningTaskTimelineEvent): string {
    return event.id;
  }

  private resetTaskForm(): void {
    this.taskForm = {
      phase_id: null,
      title: '',
      description: '',
      status: 'NO_INICIADA',
      priority: 'MEDIA',
      planned_start_date: '',
      planned_due_date: '',
      progress_percent: 0,
      sort_order: 0,
      requires_document: false,
      requires_payment: false,
    };
  }

  private clearMessages(): void {
    this.errorMessage = '';
    this.successMessage = '';
  }

  private resolveErrorMessage(error: unknown, fallback: string): string {
    const response = error as {
      error?: {
        detail?: string;
        message?: string;
        errors?: string[];
      };
      message?: string;
    };

    if (response?.error?.errors?.length) {
      return response.error.errors.join(' ');
    }

    return response?.error?.detail ||
      response?.error?.message ||
      response?.message ||
      fallback;
  }
}