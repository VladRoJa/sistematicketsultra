// frontend/src/app/internal-documents/services/internal-documents.service.ts

import { HttpClient, HttpParams, HttpResponse } from '@angular/common/http';
import { Injectable } from '@angular/core';
import { Observable } from 'rxjs';

import { environment } from 'src/environments/environment';
import {
  InternalDocument,
  InternalDocumentActionResponse,
  InternalDocumentAuditResponse,
  InternalDocumentCategoriesResponse,
  InternalDocumentCreatePayload,
  InternalDocumentListFilters,
  InternalDocumentListResponse,
  InternalDocumentReplaceVersionPayload,
  InternalDocumentsAccessResponse,
  InternalDocumentUpdatePayload,
  InternalDocumentVersionsResponse,
  InternalDocumentVisibilityPayload,
  InternalDocumentByLinkFilters,
  InternalDocumentLinkActionResponse,
  InternalDocumentLinkPayload,
  InternalDocumentLinksResponse,
} from '../models/internal-document.model';

@Injectable({
  providedIn: 'root',
})
export class InternalDocumentsService {
  private readonly baseUrl = `${environment.apiUrl}/internal-documents`;

  constructor(private http: HttpClient) {}

  getAccess(): Observable<InternalDocumentsAccessResponse> {
    return this.http.get<InternalDocumentsAccessResponse>(`${this.baseUrl}/access`);
  }

  getCategories(): Observable<InternalDocumentCategoriesResponse> {
    return this.http.get<InternalDocumentCategoriesResponse>(
      `${this.baseUrl}/categories`
    );
  }

  listDocuments(
    filters: InternalDocumentListFilters = {}
  ): Observable<InternalDocumentListResponse> {
    let params = new HttpParams();

    if (filters.q) {
      params = params.set('q', filters.q);
    }

    if (filters.category_id !== undefined && filters.category_id !== null) {
      params = params.set('category_id', String(filters.category_id));
    }

    if (filters.status) {
      params = params.set('status', filters.status);
    }

    if (
      filters.owner_department_id !== undefined &&
      filters.owner_department_id !== null
    ) {
      params = params.set(
        'owner_department_id',
        String(filters.owner_department_id)
      );
    }

    if (filters.is_sensitive !== undefined && filters.is_sensitive !== null) {
      params = params.set('is_sensitive', String(filters.is_sensitive));
    }

    if (filters.page) {
      params = params.set('page', String(filters.page));
    }

    if (filters.page_size) {
      params = params.set('page_size', String(filters.page_size));
    }

    return this.http.get<InternalDocumentListResponse>(this.baseUrl, { params });
  }

  getDocument(documentId: number): Observable<InternalDocument> {
    return this.http.get<InternalDocument>(`${this.baseUrl}/${documentId}`);
  }

  createDocument(
    payload: InternalDocumentCreatePayload
  ): Observable<InternalDocumentActionResponse> {
    const formData = new FormData();

    formData.append('file', payload.file);
    formData.append('title', payload.title);
    formData.append('category_id', String(payload.category_id));
    formData.append('is_sensitive', String(Boolean(payload.is_sensitive)));

    this.appendOptionalFormValue(formData, 'description', payload.description);
    this.appendOptionalFormValue(formData, 'document_type', payload.document_type);
    this.appendOptionalFormValue(
      formData,
      'owner_user_id',
      payload.owner_user_id
    );
    this.appendOptionalFormValue(
      formData,
      'owner_department_id',
      payload.owner_department_id
    );
    this.appendOptionalFormValue(formData, 'version_label', payload.version_label);
    this.appendOptionalFormValue(formData, 'change_notes', payload.change_notes);

    return this.http.post<InternalDocumentActionResponse>(this.baseUrl, formData);
  }

  updateDocument(
    documentId: number,
    payload: InternalDocumentUpdatePayload
  ): Observable<InternalDocumentActionResponse> {
    return this.http.patch<InternalDocumentActionResponse>(
      `${this.baseUrl}/${documentId}`,
      payload
    );
  }

  publishDocument(documentId: number): Observable<InternalDocumentActionResponse> {
    return this.http.post<InternalDocumentActionResponse>(
      `${this.baseUrl}/${documentId}/publish`,
      {}
    );
  }

  archiveDocument(documentId: number): Observable<InternalDocumentActionResponse> {
    return this.http.post<InternalDocumentActionResponse>(
      `${this.baseUrl}/${documentId}/archive`,
      {}
    );
  }

  replaceVersion(
    documentId: number,
    payload: InternalDocumentReplaceVersionPayload
  ): Observable<InternalDocumentActionResponse> {
    const formData = new FormData();

    formData.append('file', payload.file);
    formData.append('change_notes', payload.change_notes);
    this.appendOptionalFormValue(formData, 'version_label', payload.version_label);

    return this.http.post<InternalDocumentActionResponse>(
      `${this.baseUrl}/${documentId}/versions`,
      formData
    );
  }

  getVersions(documentId: number): Observable<InternalDocumentVersionsResponse> {
    return this.http.get<InternalDocumentVersionsResponse>(
      `${this.baseUrl}/${documentId}/versions`
    );
  }

  updateVisibility(
    documentId: number,
    payload: InternalDocumentVisibilityPayload
  ): Observable<InternalDocumentActionResponse> {
    return this.http.put<InternalDocumentActionResponse>(
      `${this.baseUrl}/${documentId}/visibility`,
      payload
    );
  }

  getAudit(documentId: number): Observable<InternalDocumentAuditResponse> {
    return this.http.get<InternalDocumentAuditResponse>(
      `${this.baseUrl}/${documentId}/audit`
    );
  }

  getDocumentLinks(documentId: number): Observable<InternalDocumentLinksResponse> {
    return this.http.get<InternalDocumentLinksResponse>(
      `${this.baseUrl}/${documentId}/links`
    );
  }

  createDocumentLink(
    documentId: number,
    payload: InternalDocumentLinkPayload
  ): Observable<InternalDocumentLinkActionResponse> {
    return this.http.post<InternalDocumentLinkActionResponse>(
      `${this.baseUrl}/${documentId}/links`,
      payload
    );
  }

  updateDocumentLink(
    documentId: number,
    linkId: number,
    payload: InternalDocumentLinkPayload
  ): Observable<InternalDocumentLinkActionResponse> {
    return this.http.patch<InternalDocumentLinkActionResponse>(
      `${this.baseUrl}/${documentId}/links/${linkId}`,
      payload
    );
  }

  deleteDocumentLink(
    documentId: number,
    linkId: number
  ): Observable<InternalDocumentLinkActionResponse> {
    return this.http.delete<InternalDocumentLinkActionResponse>(
      `${this.baseUrl}/${documentId}/links/${linkId}`
    );
  }

  listDocumentsByLink(
    filters: InternalDocumentByLinkFilters
  ): Observable<InternalDocumentListResponse> {
    let params = new HttpParams()
      .set('entity_type', filters.entity_type);

    if (filters.entity_id !== undefined && filters.entity_id !== null) {
      params = params.set('entity_id', String(filters.entity_id));
    }

    if (filters.entity_key) {
      params = params.set('entity_key', filters.entity_key);
    }

    if (filters.link_role) {
      params = params.set('link_role', filters.link_role);
    }

    return this.http.get<InternalDocumentListResponse>(
      `${this.baseUrl}/by-link`,
      { params }
    );
  }

  downloadCurrentDocument(documentId: number): Observable<HttpResponse<Blob>> {
    return this.http.get(`${this.baseUrl}/${documentId}/download`, {
      observe: 'response',
      responseType: 'blob',
    });
  }

  downloadHistoricalVersion(
    documentId: number,
    versionId: number
  ): Observable<HttpResponse<Blob>> {
    return this.http.get(
      `${this.baseUrl}/${documentId}/versions/${versionId}/download`,
      {
        observe: 'response',
        responseType: 'blob',
      }
    );
  }

  triggerBrowserDownload(response: HttpResponse<Blob>, fallbackName: string): void {
    const blob = response.body;

    if (!blob) {
      return;
    }

    const filename = this.resolveDownloadFilename(response, fallbackName);
    const objectUrl = window.URL.createObjectURL(blob);

    const anchor = document.createElement('a');
    anchor.href = objectUrl;
    anchor.download = filename;
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();

    window.URL.revokeObjectURL(objectUrl);
  }

  private appendOptionalFormValue(
    formData: FormData,
    key: string,
    value: string | number | boolean | null | undefined
  ): void {
    if (value === null || value === undefined || value === '') {
      return;
    }

    formData.append(key, String(value));
  }

  private resolveDownloadFilename(
    response: HttpResponse<Blob>,
    fallbackName: string
  ): string {
    const contentDisposition =
      response.headers.get('content-disposition') ||
      response.headers.get('Content-Disposition');

    if (!contentDisposition) {
      return fallbackName;
    }

    const utf8Match = /filename\*=UTF-8''([^;]+)/i.exec(contentDisposition);
    if (utf8Match?.[1]) {
      return decodeURIComponent(utf8Match[1].replace(/"/g, ''));
    }

    const normalMatch = /filename="?([^"]+)"?/i.exec(contentDisposition);
    if (normalMatch?.[1]) {
      return normalMatch[1];
    }

    return fallbackName;
  }
}