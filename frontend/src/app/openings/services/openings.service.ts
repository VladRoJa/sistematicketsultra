// frontend/src/app/openings/services/openings.service.ts


import { HttpClient, HttpParams } from '@angular/common/http';
import { Injectable } from '@angular/core';
import { Observable } from 'rxjs';

import { environment } from '../../../environments/environment';
import {
  Opening,
  OpeningCommentPayload,
  OpeningCreatePayload,
  OpeningDependencyPayload,
  OpeningListResponse,
  OpeningPhaseListResponse,
  OpeningPhasePayload,
  OpeningPhaseSingleResponse,
  OpeningSingleResponse,
  OpeningStatus,
  OpeningTaskCommentListResponse,
  OpeningTaskCommentSingleResponse,
  OpeningTaskDependencyListResponse,
  OpeningTaskDependencySingleResponse,
  OpeningTaskListResponse,
  OpeningTaskPayload,
  OpeningTaskSingleResponse,
  OpeningUpdatePayload,
  OpeningTaskBlockerImpact,
  OpeningTaskBlockerListResponse,
  OpeningTaskBlockerPayload,
  OpeningTaskBlockerResolvePayload,
  OpeningTaskBlockerSingleResponse,
  OpeningTaskBlockerStatus,
  OpeningTaskTimelineResponse,
  OpeningTaskDocumentListResponse,
  OpeningTaskDocumentUploadPayload,
  OpeningTaskDocumentUploadResponse,
  SucursalOption,
} from '../models/opening.model';

@Injectable({
  providedIn: 'root',
})
export class OpeningsService {
  private readonly baseUrl = `${environment.apiUrl}/openings`;
  private readonly sucursalesUrl = `${environment.apiUrl}/sucursales/listar`;

  constructor(private http: HttpClient) {}

  listOpenings(filters?: {
    q?: string;
    status?: OpeningStatus | 'ALL' | '';
    page?: number;
    page_size?: number;
  }): Observable<OpeningListResponse> {
    let params = new HttpParams();

    if (filters?.q) {
      params = params.set('q', filters.q);
    }

    if (filters?.status) {
      params = params.set('status', filters.status);
    }

    if (filters?.page) {
      params = params.set('page', String(filters.page));
    }

    if (filters?.page_size) {
      params = params.set('page_size', String(filters.page_size));
    }

    return this.http.get<OpeningListResponse>(this.baseUrl, { params });
  }

  getOpening(openingId: number): Observable<OpeningSingleResponse> {
    return this.http.get<OpeningSingleResponse>(`${this.baseUrl}/${openingId}`);
  }

  createOpening(payload: OpeningCreatePayload): Observable<OpeningSingleResponse> {
    return this.http.post<OpeningSingleResponse>(this.baseUrl, payload);
  }

  updateOpening(
    openingId: number,
    payload: OpeningUpdatePayload,
  ): Observable<OpeningSingleResponse> {
    return this.http.patch<OpeningSingleResponse>(`${this.baseUrl}/${openingId}`, payload);
  }

  listPhases(openingId: number): Observable<OpeningPhaseListResponse> {
    return this.http.get<OpeningPhaseListResponse>(`${this.baseUrl}/${openingId}/phases`);
  }

  createPhase(
    openingId: number,
    payload: OpeningPhasePayload,
  ): Observable<OpeningPhaseSingleResponse> {
    return this.http.post<OpeningPhaseSingleResponse>(
      `${this.baseUrl}/${openingId}/phases`,
      payload,
    );
  }

  updatePhase(
    openingId: number,
    phaseId: number,
    payload: Partial<OpeningPhasePayload>,
  ): Observable<OpeningPhaseSingleResponse> {
    return this.http.patch<OpeningPhaseSingleResponse>(
      `${this.baseUrl}/${openingId}/phases/${phaseId}`,
      payload,
    );
  }

  listTasks(openingId: number, filters?: {
    status?: string;
    phase_id?: number | null;
    owner_user_id?: number | null;
    q?: string;
  }): Observable<OpeningTaskListResponse> {
    let params = new HttpParams();

    if (filters?.status) {
      params = params.set('status', filters.status);
    }

    if (filters?.phase_id) {
      params = params.set('phase_id', String(filters.phase_id));
    }

    if (filters?.owner_user_id) {
      params = params.set('owner_user_id', String(filters.owner_user_id));
    }

    if (filters?.q) {
      params = params.set('q', filters.q);
    }

    return this.http.get<OpeningTaskListResponse>(
      `${this.baseUrl}/${openingId}/tasks`,
      { params },
    );
  }

  createTask(
    openingId: number,
    payload: OpeningTaskPayload,
  ): Observable<OpeningTaskSingleResponse> {
    return this.http.post<OpeningTaskSingleResponse>(
      `${this.baseUrl}/${openingId}/tasks`,
      payload,
    );
  }

  updateTask(
    openingId: number,
    taskId: number,
    payload: Partial<OpeningTaskPayload>,
  ): Observable<OpeningTaskSingleResponse> {
    return this.http.patch<OpeningTaskSingleResponse>(
      `${this.baseUrl}/${openingId}/tasks/${taskId}`,
      payload,
    );
  }

  listAllDependencies(openingId: number): Observable<OpeningTaskDependencyListResponse> {
    return this.http.get<OpeningTaskDependencyListResponse>(
      `${this.baseUrl}/${openingId}/task-dependencies`,
    );
  }

  listTaskDependencies(
    openingId: number,
    taskId: number,
  ): Observable<OpeningTaskDependencyListResponse> {
    return this.http.get<OpeningTaskDependencyListResponse>(
      `${this.baseUrl}/${openingId}/tasks/${taskId}/dependencies`,
    );
  }

  createTaskDependency(
    openingId: number,
    taskId: number,
    payload: OpeningDependencyPayload,
  ): Observable<OpeningTaskDependencySingleResponse> {
    return this.http.post<OpeningTaskDependencySingleResponse>(
      `${this.baseUrl}/${openingId}/tasks/${taskId}/dependencies`,
      payload,
    );
  }

  deleteTaskDependency(openingId: number, dependencyId: number): Observable<{ message: string }> {
    return this.http.delete<{ message: string }>(
      `${this.baseUrl}/${openingId}/task-dependencies/${dependencyId}`,
    );
  }

  listAllBlockers(
    openingId: number,
    filters?: {
      status?: OpeningTaskBlockerStatus | '';
      task_id?: number | null;
    },
  ): Observable<OpeningTaskBlockerListResponse> {
    let params = new HttpParams();

    if (filters?.status) {
      params = params.set('status', filters.status);
    }

    if (filters?.task_id) {
      params = params.set('task_id', String(filters.task_id));
    }

    return this.http.get<OpeningTaskBlockerListResponse>(
      `${this.baseUrl}/${openingId}/task-blockers`,
      { params },
    );
  }

  listTaskBlockers(
    openingId: number,
    taskId: number,
    filters?: {
      status?: OpeningTaskBlockerStatus | '';
    },
  ): Observable<OpeningTaskBlockerListResponse> {
    return this.listAllBlockers(openingId, {
      status: filters?.status,
      task_id: taskId,
    });
  }

  createTaskBlocker(
    openingId: number,
    taskId: number,
    payload: OpeningTaskBlockerPayload,
  ): Observable<OpeningTaskBlockerSingleResponse> {
    return this.http.post<OpeningTaskBlockerSingleResponse>(
      `${this.baseUrl}/${openingId}/tasks/${taskId}/blockers`,
      payload,
    );
  }

  resolveTaskBlocker(
    openingId: number,
    blockerId: number,
    payload: OpeningTaskBlockerResolvePayload,
  ): Observable<OpeningTaskBlockerSingleResponse> {
    return this.http.patch<OpeningTaskBlockerSingleResponse>(
      `${this.baseUrl}/${openingId}/task-blockers/${blockerId}/resolve`,
      payload,
    );
  }

  listTaskTimeline(
    openingId: number,
    taskId: number,
  ): Observable<OpeningTaskTimelineResponse> {
    return this.http.get<OpeningTaskTimelineResponse>(
      `${this.baseUrl}/${openingId}/tasks/${taskId}/timeline`,
    );
  }  

  listTaskDocuments(
    openingId: number,
    taskId: number,
  ): Observable<OpeningTaskDocumentListResponse> {
    return this.http.get<OpeningTaskDocumentListResponse>(
      `${this.baseUrl}/${openingId}/tasks/${taskId}/documents`,
    );
  }

  uploadTaskDocument(
    openingId: number,
    taskId: number,
    payload: OpeningTaskDocumentUploadPayload,
  ): Observable<OpeningTaskDocumentUploadResponse> {
    const formData = new FormData();

    formData.append('file', payload.file);
    formData.append('report_type_key', payload.report_type_key || 'internal_documents');
    formData.append('document_role', payload.document_role || 'EVIDENCE');

    if (payload.notes) {
      formData.append('notes', payload.notes);
    }

    if (payload.cutoff_date) {
      formData.append('cutoff_date', payload.cutoff_date);
    }

    return this.http.post<OpeningTaskDocumentUploadResponse>(
      `${this.baseUrl}/${openingId}/tasks/${taskId}/documents/upload`,
      formData,
    );
  }

  listTaskComments(
    openingId: number,
    taskId: number,
  ): Observable<OpeningTaskCommentListResponse> {
    return this.http.get<OpeningTaskCommentListResponse>(
      `${this.baseUrl}/${openingId}/tasks/${taskId}/comments`,
    );
  }

  createTaskComment(
    openingId: number,
    taskId: number,
    payload: OpeningCommentPayload,
  ): Observable<OpeningTaskCommentSingleResponse> {
    return this.http.post<OpeningTaskCommentSingleResponse>(
      `${this.baseUrl}/${openingId}/tasks/${taskId}/comments`,
      payload,
    );
  }

  listSucursales(): Observable<SucursalOption[]> {
    return this.http.get<SucursalOption[]>(this.sucursalesUrl);
  }

  extractOpening(response: OpeningSingleResponse): Opening {
    return response.item;
  }
}