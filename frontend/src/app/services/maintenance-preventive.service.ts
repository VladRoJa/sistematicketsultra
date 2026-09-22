import { Injectable, inject } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { Observable } from 'rxjs';

import { environment } from 'src/environments/environment';

export interface PreventiveBranch {
  id: number;
  nombre: string;
  is_demo: boolean;
}

export interface PreventiveResponsible {
  user_id: number;
  username: string;
  rol: string;
}

export interface PreventiveBuildingClassification {
  id: number;
  nombre: string;
  label: string;
  nivel: number;
}

export interface PreventiveEquipment {
  inventario_id: number;
  codigo_interno: string;
  nombre: string;
  marca: string;
  familia_equipo_id: number | null;
  familia: {
    id: number;
    key: string;
    nombre: string;
  } | null;
}

export interface PreventivePlanningContext {
  sucursales: PreventiveBranch[];
  responsables: PreventiveResponsible[];
  building_classifications: PreventiveBuildingClassification[];
}

export interface MaintenanceCrew {
  id: number;
  nombre: string;
  region_id: number | null;
  region: string | null;
  activo: boolean;
}

export interface MaintenancePersonnel {
  id: number;
  user_id: number;
  username: string;
  rol: string;
  crew_id: number | null;
  crew: string | null;
  region_id: number | null;
  activo: boolean;
}

export interface MaintenancePersonnelCatalog {
  personnel: MaintenancePersonnel[];
  candidates: Array<{
    user_id: number;
    username: string;
    rol: string;
  }>;
  crews: MaintenanceCrew[];
  regions: Array<{
    id: number;
    key: string;
    label: string;
  }>;
}

export interface PreventiveDraftItem {
  id: number;
  batch_id: number;
  source_row_number: number | null;
  target_type_input: string | null;
  sucursal_input: string | null;
  codigo_equipo_input: string | null;
  building_classification_input: string | null;
  responsable_input: string | null;
  fecha_programada_input: string | null;
  repeat_enabled_input: string | null;
  repeat_interval_workdays_input: string | null;
  target_type: 'EQUIPO' | 'EDIFICIO' | null;
  sucursal_id: number | null;
  inventario_id: number | null;
  building_classification_id: number | null;
  building_classification: PreventiveBuildingClassification | null;
  responsable_user_id: number | null;
  fecha_programada: string | null;
  repeat_enabled: boolean;
  repeat_interval_workdays: number | null;
  schedule_id: number | null;
  next_scheduled_date: string | null;
  actividad: string | null;
  observaciones: string | null;
  validation_status: 'PENDIENTE' | 'VALIDO' | 'ERROR';
  validation_errors: string[];
  ticket_id: number | null;
}

export interface PreventiveBatch {
  id: number;
  batch_key: string;
  nombre: string;
  source_type: 'MANUAL' | 'ARCHIVO';
  status: 'BORRADOR' | 'PUBLICADO' | 'CANCELADO';
  period_start: string | null;
  period_end: string | null;
  source_filename: string | null;
  source_sha256: string | null;
  notes: string | null;
  created_by_user_id: number | null;
  published_by_user_id: number | null;
  published_at: string | null;
  items: PreventiveDraftItem[];
}

export interface PreventiveBatchSummary {
  id: number;
  batch_key: string;
  nombre: string;
  source_type: 'MANUAL' | 'ARCHIVO';
  status: 'BORRADOR' | 'PUBLICADO' | 'CANCELADO';
  period_start: string | null;
  period_end: string | null;
  created_by_user_id: number | null;
  published_at: string | null;
  total: number;
  validos: number;
  errores: number;
  pendientes: number;
}

export interface PreventiveValidationSummary {
  batch_id: number;
  total: number;
  validos: number;
  errores: number;
  publicable: boolean;
}

export interface MaintenanceMyProgramItem {
  item_kind: 'TICKET' | 'RECURRENCE_PROJECTION';
  ticket_id: number | null;
  schedule_id: number | null;
  tipo_mantenimiento: 'PREVENTIVO' | 'CORRECTIVO';
  estado: string;
  operational_status:
    | 'HOY'
    | 'PROGRAMADO'
    | 'VENCIDO'
    | 'PENDIENTE_VALIDACION'
    | 'SIN_FECHA'
    | 'PREVISTO';
  fecha_trabajo: string | null;
  sucursal_id: number | null;
  sucursal: string;
  target_type: 'EQUIPO' | 'EDIFICIO' | null;
  clasificacion_id: number | null;
  inventario_id: number | null;
  codigo_equipo: string | null;
  equipo: string;
  actividad: string;
  problema_detectado: string | null;
  necesita_refaccion: boolean;
  descripcion_refaccion: string | null;
  repeat_interval_workdays: number | null;
}

export interface MaintenanceChecklistItem {
  id: number;
  item_key: string;
  etiqueta: string;
  orden: number;
  requerido: boolean;
  activo?: boolean;
}

export interface MaintenanceChecklistTemplate {
  id: number;
  template_key: string;
  familia_equipo_id: number;
  familia: string | null;
  nombre: string;
  actividad: string | null;
  activo: boolean;
  items: MaintenanceChecklistItem[];
}

export interface MaintenanceReprogramReason {
  id: number;
  key: string;
  nombre: string;
  requiere_comentario: boolean;
  activo: boolean;
  orden: number;
}

export interface MaintenanceChecklistCatalog {
  templates: MaintenanceChecklistTemplate[];
  families: Array<{
    id: number;
    key: string;
    nombre: string;
  }>;
}

export interface MaintenanceWorkBitacora {
  id: number;
  ticket_id: number | null;
  fecha: string;
  resultado: string;
  estado_encontrado: string | null;
  notas: string | null;
  checks: Record<string, string>;
  hallazgo_detectado: boolean;
  hallazgo_descripcion: string | null;
  created_by_user_id: number | null;
  created_at: string | null;
}

export interface MaintenanceDashboardMetric {
  count: number;
  ticket_ids: number[];
  percent?: number;
}

export interface MaintenanceDashboardWeek {
  week_number: number;
  week_start: string;
  week_end: string;
  preventive: {
    programmed: MaintenanceDashboardMetric;
    validated_on_time: MaintenanceDashboardMetric;
    eventually_validated: MaintenanceDashboardMetric;
    reprogrammed: MaintenanceDashboardMetric;
    missed: MaintenanceDashboardMetric;
    pending_now: MaintenanceDashboardMetric;
    strict_compliance_percent: number;
    current_progress_percent: number;
  };
  corrective: {
    due: MaintenanceDashboardMetric;
    validated_on_time: MaintenanceDashboardMetric;
    reprogrammed: MaintenanceDashboardMetric;
    missed: MaintenanceDashboardMetric;
    pending_now: MaintenanceDashboardMetric;
    demand: MaintenanceDashboardMetric;
    demand_reactive: MaintenanceDashboardMetric;
    demand_detected_preventive: MaintenanceDashboardMetric;
    fulfillment_percent: number;
  };
  backlog: {
    start: MaintenanceDashboardMetric;
    end: MaintenanceDashboardMetric;
    delta: number;
    overdue_start: MaintenanceDashboardMetric;
    overdue_end: MaintenanceDashboardMetric;
    overdue_delta: number;
  };
}

export interface MaintenanceWeeklyDashboard {
  reference_date: string;
  weeks: MaintenanceDashboardWeek[];
  filters: {
    region_id: number | null;
    branch_id: number | null;
    crew_id: number | null;
    responsible_user_id: number | null;
    branch_ids: number[];
  };
  context: {
    sucursales: Array<{
      id: number;
      nombre: string;
      region_id: number | null;
    }>;
    regiones: Array<{
      id: number;
      key: string;
      nombre: string;
    }>;
    cuadrillas: Array<{
      id: number;
      nombre: string;
      region_id: number | null;
    }>;
    responsables: Array<{
      user_id: number;
      username: string;
      crew_id: number | null;
    }>;
  };
}

export interface MaintenanceDashboardDrilldownTicket {
  id: number;
  tipo_mantenimiento: 'PREVENTIVO' | 'CORRECTIVO';
  maintenance_target_type: 'EQUIPO' | 'EDIFICIO' | null;
  origen_correctivo: string | null;
  estado: string;
  estado_cierre: string | null;
  descripcion: string;
  criticidad: number;
  asignado_a: string | null;
  sucursal_id: number | null;
  sucursal: string;
  codigo_equipo: string | null;
  equipo: string;
  fecha_creacion: string | null;
  fecha_programada_original: string | null;
  fecha_programada_actual: string | null;
  fecha_compromiso_original: string | null;
  fecha_solucion: string | null;
  fecha_validacion_cierre: string | null;
  ticket_preventivo_origen_id: number | null;
  commitment_as_of?: string | null;
  overdue_days?: number | null;
  aging_bucket?: string | null;
  reprogramaciones: Array<{
    evento: string;
    fecha_anterior: string | null;
    fecha_nueva: string | null;
    motivo_key: string | null;
    motivo: string | null;
    comentario: string | null;
    actor: string | null;
    fecha_cambio: string | null;
  }>;
}

export interface MaintenanceDashboardDrilldown {
  metric: string;
  week_start: string;
  week_end: string;
  count: number;
  aging?: {
    '1_7': number;
    '8_14': number;
    '15_30': number;
    '31_PLUS': number;
  } | null;
  tickets: MaintenanceDashboardDrilldownTicket[];
}

export interface MaintenanceWorkDetail {
  ticket: {
    id: number;
    estado: string;
    tipo_mantenimiento: string;
    fecha_programada_actual: string | null;
    sucursal_id: number | null;
    sucursal: string;
    target_type: 'EQUIPO' | 'EDIFICIO';
    clasificacion_id: number | null;
    inventario_id: number | null;
    codigo_equipo: string | null;
    equipo: string;
    actividad: string;
  };
  checklist: MaintenanceChecklistTemplate | null;
  has_evidence: boolean;
  bitacoras: MaintenanceWorkBitacora[];
}

export interface MaintenanceMyProgram {
  personnel: {
    id: number;
    user_id: number;
    username: string;
    crew_id: number | null;
    crew: string | null;
    region_id: number | null;
  };
  window: {
    start_date: string;
    end_date: string;
    today: string;
  };
  metrics: {
    today: number;
    week: number;
    projected: number;
    overdue: number;
    pending_validation: number;
    unscheduled: number;
  };
  today_items: MaintenanceMyProgramItem[];
  week_items: MaintenanceMyProgramItem[];
  projected_items: MaintenanceMyProgramItem[];
  overdue: MaintenanceMyProgramItem[];
  pending_validation: MaintenanceMyProgramItem[];
  unscheduled: MaintenanceMyProgramItem[];
}

@Injectable({ providedIn: 'root' })
export class MaintenancePreventiveService {
  private readonly http = inject(HttpClient);
  private readonly baseUrl =
    `${environment.apiUrl}/tickets/preventive-planning`;

  getReprogramReasons(
    includeInactive = false,
  ): Observable<{ reasons: MaintenanceReprogramReason[] }> {
    let params = new HttpParams();
    if (includeInactive) {
      params = params.set('include_inactive', 'true');
    }

    return this.http.get<{ reasons: MaintenanceReprogramReason[] }>(
      `${this.baseUrl}/reprogram-reasons`,
      { params },
    );
  }

  createReprogramReason(payload: {
    key: string;
    nombre: string;
    requiere_comentario?: boolean;
    orden?: number;
  }): Observable<MaintenanceReprogramReason> {
    return this.http.post<MaintenanceReprogramReason>(
      `${this.baseUrl}/reprogram-reasons`,
      payload,
    );
  }

  updateReprogramReason(
    reasonId: number,
    payload: Partial<{
      nombre: string;
      requiere_comentario: boolean;
      activo: boolean;
      orden: number;
    }>,
  ): Observable<MaintenanceReprogramReason> {
    return this.http.put<MaintenanceReprogramReason>(
      `${this.baseUrl}/reprogram-reasons/${reasonId}`,
      payload,
    );
  }

  reprogramMaintenanceTicket(
    ticketId: number,
    payload: {
      nueva_fecha: string;
      reason_id: number;
      comentario?: string | null;
    },
  ): Observable<{
    mensaje: string;
    ticket_id: number;
    tipo_mantenimiento: string;
    fecha_compromiso_original: string | null;
    fecha_solucion: string | null;
    fecha_programada_original: string | null;
    fecha_programada_actual: string | null;
  }> {
    return this.http.post<any>(
      `${this.baseUrl}/tickets/${ticketId}/reprogram`,
      payload,
    );
  }

  getWeeklyDashboard(params?: {
    weeks?: number;
    reference_date?: string;
    region_id?: number | null;
    branch_id?: number | null;
    crew_id?: number | null;
    responsible_user_id?: number | null;
  }): Observable<MaintenanceWeeklyDashboard> {
    let httpParams = new HttpParams();

    if (params?.weeks) {
      httpParams = httpParams.set('weeks', String(params.weeks));
    }
    if (params?.reference_date) {
      httpParams = httpParams.set(
        'reference_date',
        params.reference_date,
      );
    }
    if (params?.region_id) {
      httpParams = httpParams.set(
        'region_id',
        String(params.region_id),
      );
    }
    if (params?.branch_id) {
      httpParams = httpParams.set(
        'branch_id',
        String(params.branch_id),
      );
    }
    if (params?.crew_id) {
      httpParams = httpParams.set(
        'crew_id',
        String(params.crew_id),
      );
    }
    if (params?.responsible_user_id) {
      httpParams = httpParams.set(
        'responsible_user_id',
        String(params.responsible_user_id),
      );
    }

    return this.http.get<MaintenanceWeeklyDashboard>(
      `${this.baseUrl}/dashboard/weekly`,
      { params: httpParams },
    );
  }

  getDashboardDrilldown(params: {
    week_start: string;
    metric: string;
    region_id?: number | null;
    branch_id?: number | null;
    crew_id?: number | null;
    responsible_user_id?: number | null;
  }): Observable<MaintenanceDashboardDrilldown> {
    let httpParams = new HttpParams()
      .set('week_start', params.week_start)
      .set('metric', params.metric);

    if (params.region_id) {
      httpParams = httpParams.set(
        'region_id',
        String(params.region_id),
      );
    }
    if (params.branch_id) {
      httpParams = httpParams.set(
        'branch_id',
        String(params.branch_id),
      );
    }
    if (params.crew_id) {
      httpParams = httpParams.set(
        'crew_id',
        String(params.crew_id),
      );
    }
    if (params.responsible_user_id) {
      httpParams = httpParams.set(
        'responsible_user_id',
        String(params.responsible_user_id),
      );
    }

    return this.http.get<MaintenanceDashboardDrilldown>(
      `${this.baseUrl}/dashboard/drilldown`,
      { params: httpParams },
    );
  }

  getChecklistCatalog(): Observable<MaintenanceChecklistCatalog> {
    return this.http.get<MaintenanceChecklistCatalog>(
      `${this.baseUrl}/checklists`,
    );
  }

  createChecklist(payload: {
    familia_equipo_id: number;
    nombre: string;
    actividad?: string | null;
    items?: Array<{
      etiqueta: string;
      requerido?: boolean;
    }>;
  }): Observable<MaintenanceChecklistTemplate> {
    return this.http.post<MaintenanceChecklistTemplate>(
      `${this.baseUrl}/checklists`,
      payload,
    );
  }

  updateChecklist(
    templateId: number,
    payload: Partial<{
      nombre: string;
      actividad: string | null;
      activo: boolean;
    }>,
  ): Observable<MaintenanceChecklistTemplate> {
    return this.http.put<MaintenanceChecklistTemplate>(
      `${this.baseUrl}/checklists/${templateId}`,
      payload,
    );
  }

  addChecklistItem(
    templateId: number,
    payload: {
      etiqueta: string;
      requerido?: boolean;
    },
  ): Observable<MaintenanceChecklistItem> {
    return this.http.post<MaintenanceChecklistItem>(
      `${this.baseUrl}/checklists/${templateId}/items`,
      payload,
    );
  }

  updateChecklistItem(
    templateId: number,
    itemId: number,
    payload: Partial<{
      etiqueta: string;
      orden: number;
      requerido: boolean;
      activo: boolean;
    }>,
  ): Observable<MaintenanceChecklistItem> {
    return this.http.put<MaintenanceChecklistItem>(
      `${this.baseUrl}/checklists/${templateId}/items/${itemId}`,
      payload,
    );
  }

  getWorkDetail(ticketId: number): Observable<MaintenanceWorkDetail> {
    return this.http.get<MaintenanceWorkDetail>(
      `${this.baseUrl}/my-program/${ticketId}`,
    );
  }

  createWorkBitacora(
    ticketId: number,
    payload: {
      estado_encontrado: 'BUENO' | 'REQUIERE_ATENCION' | 'FUERA_SERVICIO';
      notas: string;
      checks: Record<string, string>;
      hallazgo_detectado: boolean;
      hallazgo_descripcion?: string | null;
      generar_correctivo?: boolean;
      criticidad_correctivo?: number;
    },
  ): Observable<{
    mensaje: string;
    bitacora_id: number;
    correctivo_id: number | null;
  }> {
    return this.http.post<{
      mensaje: string;
      bitacora_id: number;
      correctivo_id: number | null;
    }>(
      `${this.baseUrl}/my-program/${ticketId}/bitacora`,
      payload,
    );
  }

  uploadWorkEvidence(
    ticketId: number,
    image: File,
  ): Observable<{ mensaje: string; attachment_id: number }> {
    const formData = new FormData();
    formData.append('image', image, image.name);

    return this.http.post<{
      mensaje: string;
      attachment_id: number;
    }>(
      `${this.baseUrl}/my-program/${ticketId}/evidence`,
      formData,
    );
  }

  completeWork(ticketId: number): Observable<{
    mensaje: string;
    ticket_id: number;
    estado: string;
    estado_cierre: string;
  }> {
    return this.http.post<{
      mensaje: string;
      ticket_id: number;
      estado: string;
      estado_cierre: string;
    }>(
      `${this.baseUrl}/my-program/${ticketId}/complete`,
      {},
    );
  }

  getMyProgram(params?: {
    start_date?: string;
    end_date?: string;
  }): Observable<MaintenanceMyProgram> {
    let httpParams = new HttpParams();

    if (params?.start_date) {
      httpParams = httpParams.set('start_date', params.start_date);
    }
    if (params?.end_date) {
      httpParams = httpParams.set('end_date', params.end_date);
    }

    return this.http.get<MaintenanceMyProgram>(
      `${this.baseUrl}/my-program`,
      { params: httpParams },
    );
  }

  getPersonnelCatalog(): Observable<MaintenancePersonnelCatalog> {
    return this.http.get<MaintenancePersonnelCatalog>(
      `${this.baseUrl}/personnel`,
    );
  }

  createCrew(payload: {
    nombre: string;
    region_id?: number | null;
  }): Observable<MaintenanceCrew> {
    return this.http.post<MaintenanceCrew>(
      `${this.baseUrl}/crews`,
      payload,
    );
  }

  updateCrew(
    crewId: number,
    payload: Partial<{
      nombre: string;
      region_id: number | null;
      activo: boolean;
    }>,
  ): Observable<MaintenanceCrew> {
    return this.http.put<MaintenanceCrew>(
      `${this.baseUrl}/crews/${crewId}`,
      payload,
    );
  }

  createPersonnel(payload: {
    user_id: number;
    crew_id?: number | null;
  }): Observable<{ id: number }> {
    return this.http.post<{ id: number }>(
      `${this.baseUrl}/personnel`,
      payload,
    );
  }

  updatePersonnel(
    personnelId: number,
    payload: Partial<{
      crew_id: number | null;
      activo: boolean;
    }>,
  ): Observable<{ id: number }> {
    return this.http.put<{ id: number }>(
      `${this.baseUrl}/personnel/${personnelId}`,
      payload,
    );
  }

  getContext(): Observable<PreventivePlanningContext> {
    return this.http.get<PreventivePlanningContext>(
      `${this.baseUrl}/context`,
    );
  }

  getEquipment(branchId: number): Observable<{ equipos: PreventiveEquipment[] }> {
    const params = new HttpParams().set('branch_id', String(branchId));
    return this.http.get<{ equipos: PreventiveEquipment[] }>(
      `${this.baseUrl}/equipment`,
      { params },
    );
  }

  listBatches(): Observable<{ batches: PreventiveBatchSummary[] }> {
    return this.http.get<{ batches: PreventiveBatchSummary[] }>(
      `${this.baseUrl}/batches`,
    );
  }

  getBatch(batchId: number): Observable<PreventiveBatch> {
    return this.http.get<PreventiveBatch>(
      `${this.baseUrl}/batches/${batchId}`,
    );
  }

  createBatch(payload: {
    nombre: string;
    source_type: 'MANUAL' | 'ARCHIVO';
    period_start?: string | null;
    period_end?: string | null;
    notes?: string | null;
  }): Observable<PreventiveBatch> {
    return this.http.post<PreventiveBatch>(
      `${this.baseUrl}/batches`,
      payload,
    );
  }

  addItems(
    batchId: number,
    items: Array<{
      target_type?: 'EQUIPO' | 'EDIFICIO';
      sucursal: string;
      codigo_equipo?: string | null;
      building_classification_id?: number | null;
      responsable: string;
      fecha_programada: string;
      repeat_enabled?: boolean;
      repeat_interval_workdays?: number | null;
      actividad: string;
      observaciones?: string | null;
    }>,
  ): Observable<PreventiveBatch> {
    return this.http.post<PreventiveBatch>(
      `${this.baseUrl}/batches/${batchId}/items`,
      { items },
    );
  }

  updateItem(
    batchId: number,
    itemId: number,
    payload: Partial<{
      target_type: 'EQUIPO' | 'EDIFICIO' | string;
      sucursal: string;
      codigo_equipo: string | null;
      building_classification_id: number | string | null;
      responsable: string;
      fecha_programada: string;
      repeat_enabled: boolean | string;
      repeat_interval_workdays: number | string | null;
      actividad: string;
      observaciones: string | null;
    }>,
  ): Observable<{ mensaje: string; item: { id: number; validation_status: string } }> {
    return this.http.put<{
      mensaje: string;
      item: { id: number; validation_status: string };
    }>(
      `${this.baseUrl}/batches/${batchId}/items/${itemId}`,
      payload,
    );
  }

  deleteItem(batchId: number, itemId: number): Observable<{ mensaje: string }> {
    return this.http.delete<{ mensaje: string }>(
      `${this.baseUrl}/batches/${batchId}/items/${itemId}`,
    );
  }

  validateBatch(batchId: number): Observable<{
    summary: PreventiveValidationSummary;
    batch: PreventiveBatch;
  }> {
    return this.http.post<{
      summary: PreventiveValidationSummary;
      batch: PreventiveBatch;
    }>(
      `${this.baseUrl}/batches/${batchId}/validate`,
      {},
    );
  }

  publishBatch(batchId: number): Observable<{
    mensaje: string;
    ticket_ids: number[];
    batch: PreventiveBatch;
  }> {
    return this.http.post<{
      mensaje: string;
      ticket_ids: number[];
      batch: PreventiveBatch;
    }>(
      `${this.baseUrl}/batches/${batchId}/publish`,
      {},
    );
  }

  importBatch(
    file: File,
    metadata?: {
      nombre?: string;
      period_start?: string;
      period_end?: string;
      notes?: string;
    },
  ): Observable<{
    summary: PreventiveValidationSummary;
    batch: PreventiveBatch;
  }> {
    const formData = new FormData();
    formData.append('file', file, file.name);

    if (metadata?.nombre) {
      formData.append('nombre', metadata.nombre);
    }
    if (metadata?.period_start) {
      formData.append('period_start', metadata.period_start);
    }
    if (metadata?.period_end) {
      formData.append('period_end', metadata.period_end);
    }
    if (metadata?.notes) {
      formData.append('notes', metadata.notes);
    }

    return this.http.post<{
      summary: PreventiveValidationSummary;
      batch: PreventiveBatch;
    }>(
      `${this.baseUrl}/imports`,
      formData,
    );
  }

  downloadTemplate(): Observable<Blob> {
    return this.http.get(
      `${this.baseUrl}/template`,
      { responseType: 'blob' },
    );
  }
}
