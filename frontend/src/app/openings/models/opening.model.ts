// frontend/src/app/openings/models/opening.model.ts


export type OpeningStatus =
  | 'BORRADOR'
  | 'PLANEADA'
  | 'EN_EJECUCION'
  | 'EN_RIESGO'
  | 'PAUSADA'
  | 'ABIERTA'
  | 'CANCELADA'
  | 'CERRADA';

export type OpeningPhaseStatus =
  | 'NO_INICIADA'
  | 'EN_PROCESO'
  | 'BLOQUEADA'
  | 'EN_RIESGO'
  | 'COMPLETADA'
  | 'CANCELADA';

export type OpeningTaskStatus =
  | 'NO_INICIADA'
  | 'EN_PROCESO'
  | 'BLOQUEADA'
  | 'EN_REVISION'
  | 'COMPLETADA'
  | 'CANCELADA';

export type OpeningTaskPriority =
  | 'BAJA'
  | 'MEDIA'
  | 'ALTA'
  | 'CRITICA';

export type OpeningDependencyType =
  | 'BLOCKER'
  | 'FINISH_TO_START'
  | 'START_TO_START'
  | 'FINISH_TO_FINISH';

export type OpeningTaskBlockerType =
  | 'TASK'
  | 'PROVIDER'
  | 'PAYMENT'
  | 'PERMIT'
  | 'DOCUMENT'
  | 'DECISION'
  | 'OTHER';

export type OpeningTaskBlockerImpact =
  | 'LOW'
  | 'MEDIUM'
  | 'HIGH'
  | 'CRITICAL';

export type OpeningTaskBlockerStatus =
  | 'ACTIVE'
  | 'RESOLVED';

export type OpeningTaskTimelineSource = 'AUDIT' | 'COMMENT';

export type OpeningTaskTimelineEventType =
  | 'AUDIT'
  | 'COMMENT'
  | 'BLOCKER'
  | 'DEPENDENCY';

export interface OpeningUserSummary {
  id: number | null;
  username: string | null;
  rol?: string | null;
}

export interface OpeningDepartmentSummary {
  id: number | null;
  nombre: string | null;
}

export interface OpeningSucursalSummary {
  sucursal_id: number;
  sucursal: string;
  serie?: string | null;
  estado?: string | null;
  municipio?: string | null;
  direccion?: string | null;
  operational_status?: string | null;
}

export interface Opening {
  id: number;
  sucursal_id: number;
  sucursal: OpeningSucursalSummary | null;
  opening_key: string;
  name: string;
  description: string | null;
  status: OpeningStatus;
  planned_start_date: string | null;
  target_opening_date: string | null;
  actual_opening_date: string | null;
  general_owner_user_id: number | null;
  general_owner_user: OpeningUserSummary | null;
  budget_authorized_total: number | null;
  budget_currency_code: string;
  created_by: number | null;
  updated_by: number | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface OpeningPhase {
  id: number;
  opening_id: number;
  name: string;
  description: string | null;
  sort_order: number;
  planned_start_date: string | null;
  planned_end_date: string | null;
  actual_start_date: string | null;
  actual_end_date: string | null;
  status: OpeningPhaseStatus;
  owner_department_id: number | null;
  owner_department: OpeningDepartmentSummary | null;
  owner_user_id: number | null;
  owner_user: OpeningUserSummary | null;
  progress_percent: number | null;
  created_by: number | null;
  updated_by: number | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface OpeningTask {
  id: number;
  opening_id: number;
  phase_id: number | null;
  phase: OpeningPhase | null;
  parent_task_id: number | null;
  title: string;
  description: string | null;
  status: OpeningTaskStatus;
  priority: OpeningTaskPriority;
  owner_user_id: number | null;
  owner_user: OpeningUserSummary | null;
  owner_department_id: number | null;
  owner_department: OpeningDepartmentSummary | null;
  planned_start_date: string | null;
  planned_due_date: string | null;
  actual_start_date: string | null;
  actual_completed_at: string | null;
  progress_percent: number | null;
  sort_order: number;
  requires_document: boolean;
  requires_payment: boolean;
  created_by: number | null;
  updated_by: number | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface OpeningTaskDependency {
  id: number;
  task_id: number;
  depends_on_task_id: number;
  dependency_type: OpeningDependencyType;
  task: Pick<OpeningTask, 'id' | 'title' | 'status'> | null;
  depends_on_task: Pick<OpeningTask, 'id' | 'title' | 'status'> | null;
  created_by: number | null;
  created_at: string | null;
}

export interface OpeningTaskSummary {
  id: number;
  opening_id: number;
  phase_id: number | null;
  title: string;
  status: OpeningTaskStatus;
  priority: OpeningTaskPriority;
  planned_start_date: string | null;
  planned_due_date: string | null;
  progress_percent: number | null;
}

export interface OpeningTaskBlocker {
  id: number;
  opening_id: number;
  blocked_task_id: number;
  blocked_task: OpeningTaskSummary | null;
  blocker_type: OpeningTaskBlockerType;
  blocking_task_id: number | null;
  blocking_task: OpeningTaskSummary | null;
  reason: string;
  impact_level: OpeningTaskBlockerImpact;
  status: OpeningTaskBlockerStatus;
  created_by: number | null;
  creator: OpeningUserSummary | null;
  resolved_by: number | null;
  resolver: OpeningUserSummary | null;
  created_at: string | null;
  resolved_at: string | null;
  resolution_comment: string | null;
}

export interface OpeningTaskComment {
  id: number;
  opening_id: number;
  task_id: number;
  comment: string;
  is_system_event: boolean;
  created_by: number | null;
  creator: OpeningUserSummary | null;
  created_at: string | null;
}

export interface OpeningTaskDocumentUploadSummary {
  id: number;
  original_filename: string;
  stored_filename: string;
  file_size_bytes: number;
  file_hash_sha256: string;
  mime_type: string | null;
  extension: string;
  status: string;
  report_type_key: string | null;
  report_type_label: string | null;
  uploaded_by_user_id: number | null;
  uploaded_by_username: string | null;
  created_at: string | null;
  download_url: string | null;
}

export interface OpeningTaskDocumentLink {
  id: number;
  opening_id: number;
  task_id: number;
  warehouse_upload_id: number;
  document_role: string;
  notes: string | null;
  status: string;
  linked_by: number | null;
  linked_by_user: OpeningUserSummary | null;
  linked_at: string | null;
  unlinked_by: number | null;
  unlinked_by_user: OpeningUserSummary | null;
  unlinked_at: string | null;
  upload: OpeningTaskDocumentUploadSummary | null;
}

export interface OpeningTaskDocumentListResponse {
  items: OpeningTaskDocumentLink[];
}

export interface OpeningTaskDocumentUploadPayload {
  file: File;
  report_type_key?: string;
  document_role?: string;
  notes?: string | null;
  cutoff_date?: string | null;
}

export interface OpeningTaskDocumentUploadResponse {
  message: string;
  item: OpeningTaskDocumentLink;
  upload: {
    upload_id: number;
    filename: string;
    stored_filename: string;
    stored_path: string;
    file_size_bytes: number;
    file_hash_sha256: string;
    report_type_key: string;
    report_type_id: number;
    family_id: number;
    source_id: number;
    operational_role_id: number;
    period_type: string;
    cutoff_date: string | null;
    date_from: string | null;
    date_to: string | null;
    duplicate_detected: boolean;
    duplicate_upload_id: number | null;
  };
}

export interface OpeningListResponse {
  items: Opening[];
  page: number;
  page_size: number;
  total: number;
  total_pages: number;
  has_next: boolean;
  has_prev: boolean;
}

export interface OpeningSingleResponse {
  item: Opening;
  message?: string;
}

export interface OpeningPhaseListResponse {
  items: OpeningPhase[];
}

export interface OpeningPhaseSingleResponse {
  item: OpeningPhase;
  message?: string;
}

export interface OpeningTaskListResponse {
  items: OpeningTask[];
}

export interface OpeningTaskSingleResponse {
  item: OpeningTask;
  message?: string;
}

export interface OpeningTaskDependencyListResponse {
  items: OpeningTaskDependency[];
}

export interface OpeningTaskDependencySingleResponse {
  item: OpeningTaskDependency;
  message?: string;
}

export interface OpeningTaskBlockerListResponse {
  items: OpeningTaskBlocker[];
}

export interface OpeningTaskBlockerSingleResponse {
  item: OpeningTaskBlocker;
  message?: string;
}

export interface OpeningTaskCommentListResponse {
  items: OpeningTaskComment[];
}

export interface OpeningTaskCommentSingleResponse {
  item: OpeningTaskComment;
  message?: string;
}

export interface OpeningCreatePayload {
  sucursal_id: number | null;
  opening_key: string;
  name: string;
  description?: string | null;
  status?: OpeningStatus;
  planned_start_date?: string | null;
  target_opening_date?: string | null;
  actual_opening_date?: string | null;
  general_owner_user_id?: number | null;
  budget_authorized_total?: number | null;
  budget_currency_code?: string;
}

export type OpeningUpdatePayload = Partial<OpeningCreatePayload>;

export interface OpeningPhasePayload {
  name: string;
  description?: string | null;
  sort_order?: number;
  planned_start_date?: string | null;
  planned_end_date?: string | null;
  actual_start_date?: string | null;
  actual_end_date?: string | null;
  status?: OpeningPhaseStatus;
  owner_department_id?: number | null;
  owner_user_id?: number | null;
  progress_percent?: number;
}

export interface OpeningTaskPayload {
  phase_id?: number | null;
  parent_task_id?: number | null;
  title: string;
  description?: string | null;
  status?: OpeningTaskStatus;
  priority?: OpeningTaskPriority;
  owner_user_id?: number | null;
  owner_department_id?: number | null;
  planned_start_date?: string | null;
  planned_due_date?: string | null;
  actual_start_date?: string | null;
  progress_percent?: number;
  sort_order?: number;
  requires_document?: boolean;
  requires_payment?: boolean;
}

export interface OpeningDependencyPayload {
  depends_on_task_id: number;
  dependency_type?: OpeningDependencyType;
}

export interface OpeningTaskBlockerPayload {
  blocker_type: OpeningTaskBlockerType;
  impact_level: OpeningTaskBlockerImpact;
  reason: string;
  blocking_task_id?: number | null;
}

export interface OpeningTaskBlockerResolvePayload {
  resolution_comment?: string | null;
}

export interface OpeningCommentPayload {
  comment: string;
  is_system_event?: boolean;
}

export interface OpeningTaskTimelineEvent {
  id: string;
  source: OpeningTaskTimelineSource;
  event_type: OpeningTaskTimelineEventType | string;
  action: string;
  title: string;
  description: string;
  created_at: string | null;
  actor: OpeningUserSummary | null;
  entity_type: string;
  entity_id: number | null;
  old_value_json: Record<string, unknown> | null;
  new_value_json: Record<string, unknown> | null;
  metadata_json: Record<string, unknown> | null;
}

export interface OpeningTaskTimelineResponse {
  items: OpeningTaskTimelineEvent[];
}

export interface SucursalOption {
  sucursal_id: number;
  sucursal: string;
  operational_status?: string | null;
}