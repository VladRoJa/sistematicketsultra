// frontend/src/app/internal-documents/pages/internal-documents-home/internal-documents-home.component.ts

import { CommonModule } from '@angular/common';
import { Component, OnDestroy, OnInit } from '@angular/core';
import { DomSanitizer, SafeResourceUrl } from '@angular/platform-browser';
import { FormsModule } from '@angular/forms';

import {
  InternalDocument,
  InternalDocumentCategory,
  InternalDocumentCreatePayload,
  InternalDocumentListFilters,
  InternalDocumentStatus,
  InternalDocumentVisibilityPayload,
} from '../../models/internal-document.model';
import { InternalDocumentsService } from '../../services/internal-documents.service';

@Component({
  selector: 'app-internal-documents-home',
  standalone: true,
  imports: [
    CommonModule,
    FormsModule,
  ],
  templateUrl: './internal-documents-home.component.html',
  styleUrls: ['./internal-documents-home.component.css'],
})
export class InternalDocumentsHomeComponent implements OnInit, OnDestroy  {
  loading = false;
  saving = false;
  errorMessage = '';
  successMessage = '';

  canManage = false;

  documents: InternalDocument[] = [];
  categories: InternalDocumentCategory[] = [];

  selectedDocument: InternalDocument | null = null;

  filters: InternalDocumentListFilters = {
    q: '',
    category_id: null,
    status: 'ALL',
    page: 1,
    page_size: 25,
  };

  total = 0;
  page = 1;
  pageSize = 25;
  totalPages = 0;
  hasNext = false;
  hasPrev = false;

  selectedFile: File | null = null;
  versionFile: File | null = null;
  previewOpen = false;
  previewLoading = false;
  previewErrorMessage = '';
  previewTitle = '';
  previewType: 'pdf' | 'image' | null = null;
  previewObjectUrl: string | null = null;
  previewSafeUrl: SafeResourceUrl | null = null;
  previewDocument: InternalDocument | null = null;

  form = {
    title: '',
    description: '',
    category_id: null as number | null,
    document_type: '',
    owner_user_id: null as number | null,
    owner_department_id: null as number | null,
    is_sensitive: false,
    version_label: '1.0',
    change_notes: 'Versión inicial',
  };

  versionForm = {
    version_label: '',
    change_notes: '',
  };

  readonly statusOptions: Array<InternalDocumentStatus | 'ALL'> = [
    'ALL',
    'BORRADOR',
    'PUBLICADO',
    'ARCHIVADO',
  ];

  constructor(
    private internalDocumentsService: InternalDocumentsService,
    private sanitizer: DomSanitizer,
  ) {}

  ngOnInit(): void {
    this.loadAccess();
    this.loadCategories();
    this.loadDocuments();
  }

  ngOnDestroy(): void {
    this.revokePreviewObjectUrl();
  }

  loadAccess(): void {
    this.internalDocumentsService.getAccess().subscribe({
      next: (response) => {
        this.canManage = Boolean(response?.can_manage);
      },
      error: () => {
        this.canManage = false;
      },
    });
  }

  loadCategories(): void {
    this.internalDocumentsService.getCategories().subscribe({
      next: (response) => {
        this.categories = response.items || [];

        if (!this.form.category_id && this.categories.length > 0) {
          this.form.category_id = this.categories[0].id;
        }
      },
      error: () => {
        this.errorMessage = 'No se pudieron cargar las categorías.';
      },
    });
  }

  loadDocuments(): void {
    this.loading = true;
    this.clearMessages();

    this.internalDocumentsService.listDocuments(this.buildFilters()).subscribe({
      next: (response) => {
        this.documents = response.items || [];
        this.page = response.page;
        this.pageSize = response.page_size;
        this.total = response.total;
        this.totalPages = response.total_pages;
        this.hasNext = response.has_next;
        this.hasPrev = response.has_prev;
        this.loading = false;

        if (this.selectedDocument) {
          const refreshed = this.documents.find(
            (item) => item.id === this.selectedDocument?.id
          );
          this.selectedDocument = refreshed || this.selectedDocument;
        }
      },
      error: () => {
        this.loading = false;
        this.errorMessage = 'No se pudieron cargar los documentos.';
      },
    });
  }

  applyFilters(): void {
    this.filters.page = 1;
    this.loadDocuments();
  }

  clearFilters(): void {
    this.filters = {
      q: '',
      category_id: null,
      status: this.canManage ? 'ALL' : null,
      page: 1,
      page_size: 25,
    };

    this.loadDocuments();
  }

  goToPreviousPage(): void {
    if (!this.hasPrev) {
      return;
    }

    this.filters.page = Math.max((this.filters.page || 1) - 1, 1);
    this.loadDocuments();
  }

  goToNextPage(): void {
    if (!this.hasNext) {
      return;
    }

    this.filters.page = (this.filters.page || 1) + 1;
    this.loadDocuments();
  }

  selectDocument(document: InternalDocument): void {
    this.loading = true;
    this.clearMessages();

    this.internalDocumentsService.getDocument(document.id).subscribe({
      next: (item) => {
        this.selectedDocument = item;
        this.loading = false;
      },
      error: () => {
        this.loading = false;
        this.errorMessage = 'No se pudo cargar el detalle del documento.';
      },
    });
  }

  onFileSelected(event: Event): void {
    const input = event.target as HTMLInputElement;
    this.selectedFile = input.files?.[0] || null;
  }

  onVersionFileSelected(event: Event): void {
    const input = event.target as HTMLInputElement;
    this.versionFile = input.files?.[0] || null;
  }

  createDraft(): void {
    if (!this.canManage) {
      this.errorMessage = 'No tienes permiso para crear documentos.';
      return;
    }

    if (!this.selectedFile) {
      this.errorMessage = 'Selecciona un archivo.';
      return;
    }

    if (!this.form.title.trim()) {
      this.errorMessage = 'El título es obligatorio.';
      return;
    }

    if (!this.form.category_id) {
      this.errorMessage = 'Selecciona una categoría.';
      return;
    }

    const payload: InternalDocumentCreatePayload = {
      file: this.selectedFile,
      title: this.form.title.trim(),
      description: this.form.description.trim() || null,
      category_id: this.form.category_id,
      document_type: this.form.document_type.trim() || null,
      owner_user_id: this.form.owner_user_id,
      owner_department_id: this.form.owner_department_id,
      is_sensitive: this.form.is_sensitive,
      version_label: this.form.version_label.trim() || '1.0',
      change_notes: this.form.change_notes.trim() || 'Versión inicial',
    };

    this.saving = true;
    this.clearMessages();

    this.internalDocumentsService.createDocument(payload).subscribe({
      next: (response) => {
        this.saving = false;
        this.successMessage = response.message || 'Documento creado.';
        this.selectedDocument = response.item;
        this.resetCreateForm();
        this.loadDocuments();
      },
      error: (error) => {
        this.saving = false;
        this.errorMessage = this.resolveErrorMessage(
          error,
          'No se pudo crear el documento.'
        );
      },
    });
  }

  setGlobalVisibility(document: InternalDocument): void {
    if (!this.canManage) {
      return;
    }

    const payload: InternalDocumentVisibilityPayload = {
      visibility_mode: 'GLOBAL',
      rules: [],
    };

    this.saving = true;
    this.clearMessages();

    this.internalDocumentsService.updateVisibility(document.id, payload).subscribe({
      next: (response) => {
        this.saving = false;
        this.successMessage = response.message || 'Visibilidad actualizada.';
        this.selectedDocument = response.item;
        this.loadDocuments();
      },
      error: (error) => {
        this.saving = false;
        this.errorMessage = this.resolveErrorMessage(
          error,
          'No se pudo actualizar la visibilidad.'
        );
      },
    });
  }

  publishDocument(document: InternalDocument): void {
    if (!this.canManage) {
      return;
    }

    this.saving = true;
    this.clearMessages();

    this.internalDocumentsService.publishDocument(document.id).subscribe({
      next: (response) => {
        this.saving = false;
        this.successMessage = response.message || 'Documento publicado.';
        this.selectedDocument = response.item;
        this.loadDocuments();
      },
      error: (error) => {
        this.saving = false;
        this.errorMessage = this.resolveErrorMessage(
          error,
          'No se pudo publicar el documento.'
        );
      },
    });
  }

  archiveDocument(document: InternalDocument): void {
    if (!this.canManage) {
      return;
    }

    const confirmed = window.confirm(
      `¿Archivar el documento "${document.title}"?`
    );

    if (!confirmed) {
      return;
    }

    this.saving = true;
    this.clearMessages();

    this.internalDocumentsService.archiveDocument(document.id).subscribe({
      next: (response) => {
        this.saving = false;
        this.successMessage = response.message || 'Documento archivado.';
        this.selectedDocument = response.item;
        this.loadDocuments();
      },
      error: (error) => {
        this.saving = false;
        this.errorMessage = this.resolveErrorMessage(
          error,
          'No se pudo archivar el documento.'
        );
      },
    });
  }

  replaceVersion(document: InternalDocument): void {
    if (!this.canManage) {
      return;
    }

    if (!this.versionFile) {
      this.errorMessage = 'Selecciona el archivo de la nueva versión.';
      return;
    }

    if (!this.versionForm.change_notes.trim()) {
      this.errorMessage = 'Las notas de cambio son obligatorias.';
      return;
    }

    this.saving = true;
    this.clearMessages();

    this.internalDocumentsService.replaceVersion(document.id, {
      file: this.versionFile,
      version_label: this.versionForm.version_label.trim() || null,
      change_notes: this.versionForm.change_notes.trim(),
    }).subscribe({
      next: (response) => {
        this.saving = false;
        this.successMessage = response.message || 'Versión reemplazada.';
        this.selectedDocument = response.item;
        this.versionFile = null;
        this.versionForm = {
          version_label: '',
          change_notes: '',
        };
        this.loadDocuments();
      },
      error: (error) => {
        this.saving = false;
        this.errorMessage = this.resolveErrorMessage(
          error,
          'No se pudo reemplazar la versión.'
        );
      },
    });
  }

  downloadDocument(document: InternalDocument): void {
    this.clearMessages();

    this.internalDocumentsService.downloadCurrentDocument(document.id).subscribe({
      next: (response) => {
        this.internalDocumentsService.triggerBrowserDownload(
          response,
          this.buildFallbackDownloadName(document)
        );
      },
      error: (error) => {
        this.errorMessage = this.resolveErrorMessage(
          error,
          'No se pudo descargar el documento.'
        );
      },
    });
  }

  openPreview(document: InternalDocument): void {
    this.clearMessages();
    this.closePreview(false);

    const previewType = this.resolvePreviewType(document);

    if (!previewType) {
      this.errorMessage = 'Este formato solo está disponible para descarga.';
      return;
    }

    this.previewOpen = true;
    this.previewLoading = true;
    this.previewErrorMessage = '';
    this.previewTitle = document.title || 'Vista previa';
    this.previewType = previewType;
    this.previewDocument = document;

    this.internalDocumentsService.downloadCurrentDocument(document.id).subscribe({
      next: (response) => {
        const blob = response.body;

        if (!blob) {
          this.previewLoading = false;
          this.previewErrorMessage = 'No se pudo cargar la vista previa.';
          return;
        }

        this.previewObjectUrl = window.URL.createObjectURL(blob);

        if (previewType === 'pdf') {
          this.previewSafeUrl = this.sanitizer.bypassSecurityTrustResourceUrl(
            this.previewObjectUrl
          );
        }

        this.previewLoading = false;
      },
      error: (error) => {
        this.previewLoading = false;
        this.previewErrorMessage = this.resolveErrorMessage(
          error,
          'No se pudo cargar la vista previa.'
        );
      },
    });
  }

  closePreview(clearError = true): void {
    this.revokePreviewObjectUrl();

    this.previewOpen = false;
    this.previewLoading = false;
    this.previewTitle = '';
    this.previewType = null;
    this.previewSafeUrl = null;
    this.previewDocument = null;

    if (clearError) {
      this.previewErrorMessage = '';
    }
  }

  canPreviewDocument(document: InternalDocument): boolean {
    return this.canDownload(document) && this.resolvePreviewType(document) !== null;
  }

  private resolvePreviewType(document: InternalDocument): 'pdf' | 'image' | null {
    const mimeType = String(document.current_version?.file_mime_type || '').toLowerCase();
    const filename = String(document.current_version?.original_filename || '').toLowerCase();

    if (mimeType === 'application/pdf' || filename.endsWith('.pdf')) {
      return 'pdf';
    }

    if (
      mimeType === 'image/png' ||
      mimeType === 'image/jpeg' ||
      filename.endsWith('.png') ||
      filename.endsWith('.jpg') ||
      filename.endsWith('.jpeg')
    ) {
      return 'image';
    }

    return null;
  }

  private revokePreviewObjectUrl(): void {
    if (!this.previewObjectUrl) {
      return;
    }

    window.URL.revokeObjectURL(this.previewObjectUrl);
    this.previewObjectUrl = null;
  }

  getCategoryName(categoryId: number | null): string {
    if (!categoryId) {
      return 'Sin categoría';
    }

    return this.categories.find((item) => item.id === categoryId)?.name || 'Sin categoría';
  }

  getStatusLabel(status: string | null): string {
    if (!status) {
      return 'Sin estado';
    }

    const labels: Record<string, string> = {
      BORRADOR: 'Borrador',
      PUBLICADO: 'Publicado',
      ARCHIVADO: 'Archivado',
    };

    return labels[status] || status;
  }

  getVisibilityLabel(mode: string | null): string {
    if (!mode) {
      return 'Sin visibilidad';
    }

    const labels: Record<string, string> = {
      PRIVATE: 'Privado',
      CUSTOM: 'Personalizado',
      GLOBAL: 'Global',
    };

    return labels[mode] || mode;
  }

  getDateTimeLabel(value: string | null | undefined, emptyLabel = 'Sin fecha'): string {
    if (!value) {
      return emptyLabel;
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

  getOwnerLabel(document: InternalDocument): string {
    if (document.owner_user?.username) {
      return document.owner_user.username;
    }

    if (document.owner_department?.nombre) {
      return document.owner_department.nombre;
    }

    return 'Sin dueño';
  }

  getCurrentVersionLabel(document: InternalDocument): string {
    return document.current_version?.version_label || 'Sin versión';
  }

  canShowAdminActions(document: InternalDocument): boolean {
    return this.canManage && Boolean(document?.capabilities?.can_edit);
  }

  canSetGlobalVisibility(document: InternalDocument): boolean {
    return this.canManage &&
      Boolean(document?.capabilities?.can_manage_visibility) &&
      document.status !== 'ARCHIVADO' &&
      document.visibility_mode !== 'GLOBAL' &&
      !document.is_sensitive;
  }

  canPublish(document: InternalDocument): boolean {
    return this.canManage &&
      Boolean(document?.capabilities?.can_publish) &&
      document.status !== 'PUBLICADO' &&
      document.status !== 'ARCHIVADO';
  }

  canArchive(document: InternalDocument): boolean {
    return this.canManage &&
      Boolean(document?.capabilities?.can_archive) &&
      document.status !== 'ARCHIVADO';
  }

  canReplaceVersion(document: InternalDocument): boolean {
    return this.canManage &&
      Boolean(document?.capabilities?.can_replace_version);
  }

  canDownload(document: InternalDocument): boolean {
    return Boolean(document?.capabilities?.can_download);
  }

  trackByDocumentId(_index: number, document: InternalDocument): number {
    return document.id;
  }

  private buildFilters(): InternalDocumentListFilters {
    return {
      q: this.filters.q || '',
      category_id: this.filters.category_id || null,
      status: this.canManage ? (this.filters.status || 'ALL') : null,
      owner_department_id: this.filters.owner_department_id || null,
      is_sensitive: this.filters.is_sensitive ?? null,
      page: this.filters.page || 1,
      page_size: this.filters.page_size || 25,
    };
  }

  private resetCreateForm(): void {
    this.selectedFile = null;
    this.form = {
      title: '',
      description: '',
      category_id: this.categories[0]?.id || null,
      document_type: '',
      owner_user_id: null,
      owner_department_id: null,
      is_sensitive: false,
      version_label: '1.0',
      change_notes: 'Versión inicial',
    };
  }

  private clearMessages(): void {
    this.errorMessage = '';
    this.successMessage = '';
  }

  private buildFallbackDownloadName(document: InternalDocument): string {
    const originalFilename = document.current_version?.original_filename?.trim();

    if (originalFilename) {
      return originalFilename;
    }

    const title = (document.title || 'documento').trim();
    const version = document.current_version?.version_label || 'vigente';
    const extension = this.resolveFallbackExtension(
      document.current_version?.file_mime_type
    );

    return `${title}_${version}${extension}`;
  }

  private resolveFallbackExtension(mimeType: string | null | undefined): string {
    const normalizedMimeType = String(mimeType || '').toLowerCase();

    const extensionsByMimeType: Record<string, string> = {
      'application/pdf': '.pdf',
      'application/vnd.openxmlformats-officedocument.wordprocessingml.document': '.docx',
      'application/vnd.openxmlformats-officedocument.presentationml.presentation': '.pptx',
      'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': '.xlsx',
      'application/vnd.ms-excel': '.xls',
      'text/csv': '.csv',
      'text/plain': '.txt',
      'image/png': '.png',
      'image/jpeg': '.jpg',
    };

    return extensionsByMimeType[normalizedMimeType] || '';
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