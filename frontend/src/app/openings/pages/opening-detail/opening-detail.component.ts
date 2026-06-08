//   frontend\src\app\openings\pages\opening-detail\opening-detail.component.ts


import { CommonModule } from '@angular/common';
import { Component, OnDestroy, OnInit } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, Router } from '@angular/router';
import { forkJoin, Subscription } from 'rxjs';

import {
  Opening,
  OpeningPhase,
  OpeningTask,
  OpeningTaskComment,
  OpeningTaskDependency,
  OpeningTaskPriority,
  OpeningTaskStatus,
} from '../../models/opening.model';
import { OpeningsService } from '../../services/openings.service';

type OpeningDetailView = 'DASHBOARD' | 'GANTT' | 'TASKS';
type GanttCellState = 'empty' | 'single' | 'start' | 'middle' | 'end';

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
  openingId = 0;

  opening: Opening | null = null;
  phases: OpeningPhase[] = [];
  tasks: OpeningTask[] = [];
  dependencies: OpeningTaskDependency[] = [];
  selectedTaskComments: OpeningTaskComment[] = [];

  selectedTask: OpeningTask | null = null;
  selectedPhaseId: number | 'ALL' = 'ALL';
  activeView: OpeningDetailView = 'DASHBOARD';

  loading = false;
  savingTask = false;
  savingComment = false;
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
    }).subscribe({
      next: ({ openingResponse, phasesResponse, tasksResponse, dependenciesResponse }) => {
        this.opening = openingResponse.item;
        this.phases = phasesResponse.items || [];
        this.tasks = tasksResponse.items || [];
        this.dependencies = dependenciesResponse.items || [];

        if (this.selectedTask) {
          const refreshedTask = this.tasks.find((task) => task.id === this.selectedTask?.id);
          this.selectedTask = refreshedTask || null;
        }

        this.loading = false;
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
    this.commentDraft = '';
    this.loadSelectedTaskComments();
  }

  closeTaskPanel(): void {
    this.selectedTask = null;
    this.selectedTaskComments = [];
    this.commentDraft = '';
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

  getBlockedTasksCount(): number {
    return this.tasks.filter((task) => task.status === 'BLOQUEADA').length;
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
    maxAllowedEnd.setDate(maxAllowedEnd.getDate() + 56);

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

  trackByPhaseId(_index: number, phase: OpeningPhase): number {
    return phase.id;
  }

  trackByTaskId(_index: number, task: OpeningTask): number {
    return task.id;
  }

  trackByDependencyId(_index: number, dependency: OpeningTaskDependency): number {
    return dependency.id;
  }

  trackByCommentId(_index: number, comment: OpeningTaskComment): number {
    return comment.id;
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