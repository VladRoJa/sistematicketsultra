// frontend/src/app/internal-documents/models/internal-document.model.ts

export interface InternalDocumentCategory {
  id: number;
  key: string;
  name: string;
  description?: string | null;
  is_active: boolean;
  sort_order: number;
}

export type InternalDocumentStatus = 'BORRADOR' | 'PUBLICADO' | 'ARCHIVADO';
export type InternalDocumentVisibilityMode = 'PRIVATE' | 'CUSTOM' | 'GLOBAL';
export type InternalDocumentVisibilityType =
  | 'GLOBAL'
  | 'ROLE'
  | 'DEPARTMENT'
  | 'SUCURSAL'
  | 'USER';

export type InternalDocumentLinkEntityType =
  | 'PROJECT'
  | 'OPENING'
  | 'TASK'
  | 'SUCURSAL'
  | 'DEPARTMENT'
  | 'GENERAL';

export type InternalDocumentLinkRole =
  | 'PLANO'
  | 'PERMISO'
  | 'CONTRATO'
  | 'COTIZACION'
  | 'CHECKLIST'
  | 'EVIDENCIA'
  | 'MANUAL'
  | 'FINANCIERO'
  | 'CONSTRUCCION'
  | 'OPERACION'
  | 'OTRO';

export type InternalDocumentExternalProvider = 'GOOGLE_DRIVE';

export type InternalDocumentExternalResourceKind =
  | 'VIDEO'
  | 'FOLDER'
  | 'LINK';

export interface InternalDocumentExternalResource {
  id: number;
  document_id: number;
  provider: InternalDocumentExternalProvider;
  resource_kind: InternalDocumentExternalResourceKind;
  original_url: string;
  external_file_id: string | null;
  preview_url: string | null;
  title: string | null;
  description: string | null;
  is_primary: boolean;
  is_active: boolean;
  created_by: number | null;
  updated_by: number | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface InternalDocumentExternalResourcePayload {
  provider?: InternalDocumentExternalProvider;
  resource_kind?: InternalDocumentExternalResourceKind;
  original_url: string;
  title?: string | null;
  description?: string | null;
  is_primary?: boolean;
}

export interface InternalDocumentExternalResourcesResponse {
  items: InternalDocumentExternalResource[];
}

export interface InternalDocumentExternalResourceActionResponse {
  message: string;
  item: InternalDocumentExternalResource;
}

export interface InternalDocumentCapabilities {
  can_view: boolean;
  can_download: boolean;
  can_edit: boolean;
  can_publish: boolean;
  can_archive: boolean;
  can_replace_version: boolean;
  can_manage_visibility: boolean;
  can_view_audit: boolean;
  can_download_historical_versions: boolean;
}

export interface InternalDocumentUserSnapshot {
  id: number | null;
  username: string | null;
  rol: string | null;
}

export interface InternalDocumentDepartmentSnapshot {
  id: number | null;
  nombre: string | null;
}

export interface InternalDocumentWarehouseUpload {
  id: number;
  original_filename: string | null;
  stored_filename: string | null;
  file_size_bytes: number | null;
  file_hash_sha256: string | null;
  mime_type: string | null;
  extension: string | null;
  report_type_id: number | null;
  period_type: string | null;
  cutoff_date: string | null;
  date_from: string | null;
  date_to: string | null;
  status: string | null;
}

export interface InternalDocumentVersion {
  id: number;
  document_id: number;
  warehouse_upload_id: number;
  version_label: string;
  version_number: number;
  original_filename: string | null;
  file_mime_type: string | null;
  file_size_bytes: number | null;
  file_hash_sha256: string | null;
  change_notes: string | null;
  is_current: boolean;
  is_hidden_from_users: boolean;
  created_by: number | null;
  created_at: string | null;
  warehouse_upload?: InternalDocumentWarehouseUpload | null;
}

export interface InternalDocumentVisibilityRule {
  id?: number;
  document_id?: number;
  visibility_type: InternalDocumentVisibilityType;
  role?: string | null;
  department_id?: number | null;
  sucursal_id?: number | null;
  user_id?: number | null;
  can_view: boolean;
  can_download: boolean;
  is_active?: boolean;
  created_by?: number | null;
  created_at?: string | null;
}

export interface InternalDocumentLink {
  id: number;
  document_id: number;
  entity_type: InternalDocumentLinkEntityType;
  entity_id: number | null;
  entity_key: string | null;
  link_role: InternalDocumentLinkRole;
  label: string | null;
  is_primary: boolean;
  is_active: boolean;
  created_by: number | null;
  updated_by: number | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface InternalDocumentLinkPayload {
  entity_type: InternalDocumentLinkEntityType;
  entity_id?: number | null;
  entity_key?: string | null;
  link_role: InternalDocumentLinkRole;
  label?: string | null;
  is_primary?: boolean;
}

export interface InternalDocumentLinksResponse {
  items: InternalDocumentLink[];
}

export interface InternalDocumentLinkActionResponse {
  message: string;
  item: InternalDocumentLink;
}

export interface InternalDocumentByLinkFilters {
  entity_type: InternalDocumentLinkEntityType;
  entity_id?: number | null;
  entity_key?: string | null;
  link_role?: InternalDocumentLinkRole | null;
}

export interface InternalDocumentAuditLog {
  id: number;
  document_id: number;
  version_id: number | null;
  actor_user_id: number | null;
  action: string;
  old_value_json: Record<string, unknown> | null;
  new_value_json: Record<string, unknown> | null;
  metadata_json: Record<string, unknown> | null;
  ip_address: string | null;
  user_agent: string | null;
  created_at: string | null;
}

export interface InternalDocument {
  id: number;
  title: string;
  description: string | null;
  category_id: number;
  category: InternalDocumentCategory | null;
  document_type: string | null;
  owner_user_id: number | null;
  owner_department_id: number | null;
  owner_user: InternalDocumentUserSnapshot | null;
  owner_department: InternalDocumentDepartmentSnapshot | null;
  status: InternalDocumentStatus;
  is_sensitive: boolean;
  current_version_id: number | null;
  current_version: InternalDocumentVersion | null;
  visibility_mode: InternalDocumentVisibilityMode;
  published_by: number | null;
  published_at: string | null;
  archived_by: number | null;
  archived_at: string | null;
  created_by: number | null;
  updated_by: number | null;
  created_at: string | null;
  updated_at: string | null;
  capabilities: InternalDocumentCapabilities;
  versions?: InternalDocumentVersion[];
  visibility_rules?: InternalDocumentVisibilityRule[];
  links?: InternalDocumentLink[];
  external_resources?: InternalDocumentExternalResource[];
  has_external_resources?: boolean;
  external_resources_count?: number;
  primary_external_resource?: InternalDocumentExternalResource | null;
}

export interface InternalDocumentsAccessResponse {
  allowed: boolean;
  module: string;
  can_manage: boolean;
  user: {
    id: number;
    username: string | null;
    role: string;
    sucursal_id: number | null;
    sucursales_ids: number[];
    department_id: number | null;
  };
}

export type InternalDocumentPeriodFilter =
  | 'today'
  | 'yesterday'
  | 'last_7_days'
  | 'month'
  | 'custom'
  | 'all';

export interface InternalDocumentListFilters {
  q?: string | null;
  category_id?: number | null;
  status?: InternalDocumentStatus | 'ALL' | null;
  owner_department_id?: number | null;
  is_sensitive?: boolean | null;

  period?: InternalDocumentPeriodFilter | null;
  date_from?: string | null;
  date_to?: string | null;

  page?: number | null;
  page_size?: number | null;

  offset?: number | null;
  limit?: number | null;
}

export interface InternalDocumentListResponse {
  offset?: number;
  limit?: number;
  returned?: number;
  has_more?: boolean;
  next_offset?: number | null;
  period?: InternalDocumentPeriodFilter | string | null;
  date_from?: string | null;
  date_to?: string | null;
  items: InternalDocument[];
  page: number;
  page_size: number;
  total: number;
  total_pages: number;
  has_next: boolean;
  has_prev: boolean;
}

export interface InternalDocumentCategoriesResponse {
  items: InternalDocumentCategory[];
}

export interface InternalDocumentCreatePayload {
  file: File;
  title: string;
  description?: string | null;
  category_id: number;
  document_type?: string | null;
  owner_user_id?: number | null;
  owner_department_id?: number | null;
  is_sensitive?: boolean;
  version_label?: string | null;
  change_notes?: string | null;
}

export interface InternalDocumentUpdatePayload {
  title?: string | null;
  description?: string | null;
  category_id?: number | null;
  document_type?: string | null;
  owner_user_id?: number | null;
  owner_department_id?: number | null;
  is_sensitive?: boolean;
}

export interface InternalDocumentReplaceVersionPayload {
  file: File;
  version_label?: string | null;
  change_notes: string;
}

export interface InternalDocumentVisibilityPayload {
  visibility_mode: InternalDocumentVisibilityMode;
  rules?: InternalDocumentVisibilityRule[];
}

export interface InternalDocumentActionResponse {
  message: string;
  item: InternalDocument;
}

export interface InternalDocumentVersionsResponse {
  items: InternalDocumentVersion[];
}

export interface InternalDocumentAuditResponse {
  items: InternalDocumentAuditLog[];
}