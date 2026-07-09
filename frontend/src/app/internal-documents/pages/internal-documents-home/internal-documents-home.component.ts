// frontend/src/app/internal-documents/pages/internal-documents-home/internal-documents-home.component.ts

import { CommonModule } from '@angular/common';
import { Component, OnDestroy, OnInit } from '@angular/core';
import { DomSanitizer, SafeResourceUrl } from '@angular/platform-browser';
import { FormsModule } from '@angular/forms';

import {
  InternalDocument,
  InternalDocumentCategory,
  InternalDocumentCreatePayload,
  InternalDocumentLink,
  InternalDocumentLinkEntityType,
  InternalDocumentLinkPayload,
  InternalDocumentLinkRole,
  InternalDocumentListFilters,
  InternalDocumentListResponse,
  InternalDocumentPeriodFilter,
  InternalDocumentStatus,
  InternalDocumentVisibilityPayload,
  InternalDocumentExternalResource,
  InternalDocumentExternalResourcePayload,
} from '../../models/internal-document.model';
import { InternalDocumentsService } from '../../services/internal-documents.service';

interface InternalDocumentDiscoveryCard {
  key: string;
  title: string;
  description: string;
  icon: string;
  query?: string;
  categoryName?: string;
  period: InternalDocumentPeriodFilter;
  children?: InternalDocumentDiscoveryCard[];
}

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
export class InternalDocumentsHomeComponent implements OnInit, OnDestroy {
  loading = false;
  saving = false;
  errorMessage = '';
  successMessage = '';

  canManage = false;
  isCreatePanelOpen = false;
  currentUserId: number | null = null;

  documents: InternalDocument[] = [];
  categories: InternalDocumentCategory[] = [];

  visiblePublishedCount = 0;
  visibleDraftCount = 0;
  visibleSensitiveCount = 0;
  visiblePreviewableCount = 0;

  selectedDocument: InternalDocument | null = null;

  filters: InternalDocumentListFilters = {
    q: '',
    category_id: null,
    status: 'ALL',
    period: 'today',
    date_from: null,
    date_to: null,
    page: 1,
    page_size: 25,
    offset: 0,
    limit: 25,
  };

  total = 0;
  page = 1;
  pageSize = 25;
  totalPages = 0;
  hasNext = false;
  hasPrev = false;
  readonly visiblePageSize = 25;
  readonly allPeriodBlockSize = 200;

  private cachedBlockSignature = '';
  private cachedBlockOffset = -1;
  private cachedBlockItems: InternalDocument[] = [];
  private cachedBlockTotal = 0;
  private cachedBlockTotalPages = 0;
  private searchDebounceTimer: ReturnType<typeof setTimeout> | null = null;
  private searchForcedAllPeriod = false;
  expandedDiscoveryCardKey: string | null = null;

  readonly searchDebounceMs = 350;

  readonly periodOptions: Array<{
    value: InternalDocumentPeriodFilter;
    label: string;
  }> = [
    { value: 'today', label: 'Hoy' },
    { value: 'yesterday', label: 'Ayer' },
    { value: 'last_7_days', label: 'Últimos 7 días' },
    { value: 'month', label: 'Este mes' },
    { value: 'all', label: 'Todo' },
    { value: 'custom', label: 'Personalizado' },
  ];

readonly discoveryCards: InternalDocumentDiscoveryCard[] = [
  {
    key: 'manuales',
    title: 'Manuales',
    description: 'Procesos, instructivos y documentación operativa.',
    icon: 'MAN',
    query: 'manual',
    categoryName: 'Manuales',
    period: 'all',
  },
  {
    key: 'formatos',
    title: 'Formatos',
    description: 'Plantillas, checklists y archivos reutilizables.',
    icon: 'FOR',
    query: 'formato',
    categoryName: 'Formatos',
    period: 'all',
  },
  {
    key: 'comunicados',
    title: 'Comunicados',
    description: 'Avisos e información interna publicada.',
    icon: 'COM',
    query: 'comunicado',
    categoryName: 'Comunicados',
    period: 'all',
  },
    {
    key: 'politicas',
    title: 'Politicas',
    description: 'Avisos e información interna publicada.',
    icon: 'POL',
    query: 'politica',
    categoryName: 'Politicas',
    period: 'all',
  },
  {
    key: 'reportes',
    title: 'Reportes',
    description: 'Archivos operativos, administrativos y de seguimiento.',
    icon: 'REP',
    query: 'reporte',
    categoryName: 'Reportes',
    period: 'all',
    children: [
      {
        key: 'reportes-cobranza',
        title: 'Cobranza recurrente',
        description: 'Archivos diarios de cobranza recurrente por sucursal.',
        icon: 'COB',
        query: 'Cobranza recurrente rechazados',
        categoryName: 'Reportes',
        period: 'all',
      },
    ],
  },
];

  selectedFile: File | null = null;
  versionFile: File | null = null;

  previewOpen = false;
  previewLoading = false;
  previewErrorMessage = '';
  previewTitle = '';
  previewType: 'pdf' | 'image' | 'drive-video' | null = null;
  previewObjectUrl: string | null = null;
  previewSafeUrl: SafeResourceUrl | null = null;
  previewDocument: InternalDocument | null = null;
  previewExternalResource: InternalDocumentExternalResource | null = null;

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

  linksSaving = false;
  isAssignDocumentModalOpen = false;
  isReplaceVersionModalOpen = false;
  pendingDeleteLink: InternalDocumentLink | null = null;
  isDeleteLinkModalOpen = false;
  externalResourcesLoading = false;
  externalResourcesSaving = false;
  externalResources: InternalDocumentExternalResource[] = [];

  externalResourceForm = {
    original_url: '',
    title: '',
    description: '',
    is_primary: true,
  };  

  linkForm = {
    entity_type: 'OPENING' as InternalDocumentLinkEntityType,
    entity_id: null as number | null,
    entity_key: '',
    link_role: 'MANUAL' as InternalDocumentLinkRole,
    label: '',
    is_primary: false,
  };

  readonly linkEntityTypeOptions: Array<{
    value: InternalDocumentLinkEntityType;
    label: string;
  }> = [
    { value: 'OPENING', label: 'Apertura' },
    { value: 'PROJECT', label: 'Proyecto' },
    { value: 'TASK', label: 'Tarea' },
    { value: 'SUCURSAL', label: 'Sucursal' },
    { value: 'DEPARTMENT', label: 'Departamento' },
    { value: 'GENERAL', label: 'General' },
  ];

  readonly linkRoleOptions: Array<{
    value: InternalDocumentLinkRole;
    label: string;
  }> = [
    { value: 'PLANO', label: 'Plano' },
    { value: 'PERMISO', label: 'Permiso' },
    { value: 'CONTRATO', label: 'Contrato' },
    { value: 'COTIZACION', label: 'Cotización' },
    { value: 'CHECKLIST', label: 'Checklist' },
    { value: 'EVIDENCIA', label: 'Evidencia' },
    { value: 'MANUAL', label: 'Manual' },
    { value: 'FINANCIERO', label: 'Financiero' },
    { value: 'CONSTRUCCION', label: 'Construcción' },
    { value: 'OPERACION', label: 'Operación' },
    { value: 'OTRO', label: 'Otro' },
  ];

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
    this.cancelScheduledSearchReload();
    this.revokePreviewObjectUrl();
  }

  loadAccess(): void {
    this.internalDocumentsService.getAccess().subscribe({
      next: (response) => {
        this.canManage = Boolean(response?.can_manage);
        this.currentUserId = response?.user?.id ?? null;

        if (!this.form.owner_user_id && this.currentUserId) {
          this.form.owner_user_id = this.currentUserId;
        }
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
    const requestFilters = this.buildFilters();
    const requestOffset = requestFilters.offset || 0;
    const requestSignature = this.buildListSignature(requestFilters);

    if (this.canUseCachedBlock(requestSignature, requestOffset)) {
      this.applyCachedBlock(requestOffset);
      return;
    }

    this.loading = true;
    this.clearMessages();

    this.internalDocumentsService.listDocuments(requestFilters).subscribe({
      next: (response) => {
        const blockItems = response.items || [];
        const responseOffset = response.offset ?? requestOffset;

        this.cachedBlockSignature = requestSignature;
        this.cachedBlockOffset = responseOffset;
        this.cachedBlockItems = blockItems;
        this.cachedBlockTotal = response.total || 0;
        this.cachedBlockTotalPages = response.total_pages || 0;

        this.applyResponseBlock(blockItems, responseOffset, response);
        this.refreshSelectedDocumentFromCurrentPage();

        this.loading = false;
      },
      error: () => {
        this.loading = false;
        this.errorMessage = 'No se pudieron cargar los documentos.';
      },
    });
  }

  applyFilters(): void {
    this.filters.page = 1;
    this.resetListCache();
    this.loadDocuments();
  }

  clearFilters(): void {
    this.cancelScheduledSearchReload();
    this.searchForcedAllPeriod = false;
    
    this.filters = {
      q: '',
      category_id: null,
      status: this.canManage ? 'ALL' : null,
      period: 'today',
      date_from: null,
      date_to: null,
      page: 1,
      page_size: this.visiblePageSize,
      offset: 0,
      limit: this.visiblePageSize,
    };

    this.resetListCache();
    this.loadDocuments();
  }

applyDiscoveryCard(card: InternalDocumentDiscoveryCard): void {
  if (card.children?.length) {
    this.expandedDiscoveryCardKey =
      this.expandedDiscoveryCardKey === card.key ? null : card.key;

    return;
  }

  this.applyDiscoveryTarget(card);
}

isDiscoveryCardActive(card: InternalDocumentDiscoveryCard): boolean {
  if (card.children?.length) {
    return this.isDiscoveryCardExpanded(card);
  }

  const currentSearch = (this.filters.q || '').trim().toLowerCase();
  const cardSearch = (card.query || '').trim().toLowerCase();
  const categoryId = this.resolveCategoryIdByName(card.categoryName);
  const hasCategoryTarget = Boolean(card.categoryName);
  const categoryWasResolved = !hasCategoryTarget || categoryId !== null;

  const isChildTarget = this.discoveryCards.some((parent) =>
    (parent.children || []).some((child) => child.key === card.key)
  );

  const expectedSearch = isChildTarget || !card.categoryName || !categoryWasResolved
    ? cardSearch
    : '';

  const matchesSearch = currentSearch === expectedSearch;
  const matchesCategory = categoryWasResolved
    ? this.filters.category_id === categoryId
    : this.filters.category_id === null;

  return matchesSearch && matchesCategory && this.filters.period === card.period;
}

  trackByDiscoveryCardKey(_index: number, card: InternalDocumentDiscoveryCard): string {
    return card.key;
  }

applyDiscoveryTarget(card: InternalDocumentDiscoveryCard): void {
  this.cancelScheduledSearchReload();
  this.searchForcedAllPeriod = false;

  const categoryId = this.resolveCategoryIdByName(card.categoryName);
  const hasCategoryTarget = Boolean(card.categoryName);
  const categoryWasResolved = !hasCategoryTarget || categoryId !== null;
  const isChildTarget = this.discoveryCards.some((parent) =>
    (parent.children || []).some((child) => child.key === card.key)
  );

  const fallbackQuery = card.query || card.title || '';
  const query = isChildTarget || !card.categoryName || !categoryWasResolved
    ? fallbackQuery
    : '';

  this.filters = {
    ...this.filters,
    q: query,
    category_id: categoryWasResolved ? categoryId : null,
    status: this.canManage ? 'ALL' : null,
    period: card.period,
    date_from: null,
    date_to: null,
    page: 1,
    page_size: this.visiblePageSize,
    offset: 0,
    limit: card.period === 'all' ? this.allPeriodBlockSize : this.visiblePageSize,
  };

  this.page = 1;
  this.selectedDocument = null;
  this.externalResources = [];

  this.resetListCache();
  this.loadDocuments();
}

isDiscoveryCardExpanded(card: InternalDocumentDiscoveryCard): boolean {
  return this.expandedDiscoveryCardKey === card.key;
}

getExpandedDiscoveryCard(): InternalDocumentDiscoveryCard | null {
  if (!this.expandedDiscoveryCardKey) {
    return null;
  }

  return this.discoveryCards.find(
    (card) => card.key === this.expandedDiscoveryCardKey
  ) || null;
}

getExpandedDiscoveryChildren(): InternalDocumentDiscoveryCard[] {
  return this.getExpandedDiscoveryCard()?.children || [];
}

private resolveCategoryIdByName(categoryName: string | null | undefined): number | null {
  if (!categoryName) {
    return null;
  }

  const normalizedCategoryName = this.normalizeDiscoveryText(categoryName);

  return this.categories.find((category) => {
    return this.normalizeDiscoveryText(category.name) === normalizedCategoryName ||
      this.normalizeDiscoveryText(category.key) === normalizedCategoryName;
  })?.id || null;
}

private normalizeDiscoveryText(value: string | null | undefined): string {
  return String(value || '')
    .trim()
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLowerCase();
}

  toggleCreatePanel(): void {
    if (!this.canManage) {
      return;
    }

    this.isCreatePanelOpen = !this.isCreatePanelOpen;
  }

  closeCreatePanel(): void {
    this.isCreatePanelOpen = false;
  }

  getCreatePanelButtonLabel(): string {
    return this.isCreatePanelOpen ? 'Cerrar formulario' : 'Nuevo documento';
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

  onPeriodChanged(): void {
    this.searchForcedAllPeriod = false;

    if (this.filters.period !== 'custom') {
      this.filters.date_from = null;
      this.filters.date_to = null;
    }

    this.page = 1;
    this.filters.page = 1;
    this.filters.offset = 0;
    this.resetListCache();
  }

  selectDocument(document: InternalDocument): void {
    this.loading = true;
    this.clearMessages();

    this.internalDocumentsService.getDocument(document.id).subscribe({
      next: (item) => {
        this.selectedDocument = item;
        this.externalResources = [];
        this.loadExternalResourcesForSelectedDocument();
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

    if (!this.form.description.trim()) {
      this.errorMessage = 'La descripción es obligatoria.';
      return;
    }

    if (!this.hasCreateDocumentOwner()) {
      this.errorMessage = 'El dueño documental es obligatorio.';
      return;
    }

    const externalResourcePayload = this.buildExternalResourcePayload({
      requireUrl: false,
    });

    if (this.errorMessage) {
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
        const createdDocument = response.item;

        if (!externalResourcePayload) {
          this.saving = false;
          this.successMessage = response.message || 'Documento creado.';
          this.selectedDocument = createdDocument;
          this.externalResources = [];
          this.resetCreateForm();
          this.closeCreatePanel();
          this.loadDocuments();
          return;
        }

        this.internalDocumentsService.createExternalResource(
          createdDocument.id,
          externalResourcePayload
        ).subscribe({
          next: (resourceResponse) => {
            this.saving = false;
            this.successMessage = 'Documento creado y video registrado.';
            this.selectedDocument = createdDocument;
            this.externalResources = resourceResponse.item ? [resourceResponse.item] : [];
            this.resetCreateForm();
            this.closeCreatePanel();
            this.loadDocuments();
          },
          error: (error) => {
            this.saving = false;
            this.selectedDocument = createdDocument;
            this.successMessage = 'Documento creado, pero no se pudo registrar el video.';
            this.errorMessage = this.resolveErrorMessage(
              error,
              'No se pudo registrar el video externo.'
            );
            this.loadDocuments();
          },
        });
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

  onSearchTextChanged(value: string): void {
    this.filters.q = value;

    const cleanSearch = (value || '').trim();

    if (cleanSearch) {
      if (this.filters.period !== 'all') {
        this.searchForcedAllPeriod = true;
        this.filters.period = 'all';
        this.filters.date_from = null;
        this.filters.date_to = null;
      }
    } else if (this.searchForcedAllPeriod) {
      this.searchForcedAllPeriod = false;
      this.filters.period = 'today';
      this.filters.date_from = null;
      this.filters.date_to = null;
    }

    this.page = 1;
    this.filters.page = 1;
    this.filters.offset = 0;

    this.scheduleSearchReload();
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
        this.applyDocumentUpdateToCurrentList(response.item);
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
        this.applyDocumentUpdateToCurrentList(response.item);
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
        this.isReplaceVersionModalOpen = false;
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

  createLinkForSelectedDocument(): void {
    if (!this.canManageLinks(this.selectedDocument)) {
      return;
    }

    const document = this.selectedDocument;

    if (!document) {
      return;
    }

    const payload = this.buildLinkPayload();

    if (!payload) {
      return;
    }

    this.linksSaving = true;
    this.clearMessages();

    this.internalDocumentsService.createDocumentLink(document.id, payload).subscribe({
      next: (response) => {
        this.linksSaving = false;
        this.successMessage = response.message || 'Vínculo documental creado.';
        this.resetLinkForm();
        this.reloadSelectedDocumentDetails(document.id);
      },
      error: (error) => {
        this.linksSaving = false;
        this.errorMessage = this.resolveErrorMessage(
          error,
          'No se pudo crear el vínculo documental.'
        );
      },
    });
  }

  deleteLinkFromSelectedDocument(link: InternalDocumentLink): void {
    if (!this.canManageLinks(this.selectedDocument) || !this.selectedDocument) {
      return;
    }

    this.pendingDeleteLink = link;
    this.isDeleteLinkModalOpen = true;
  }

  cancelDeleteLinkRemoval(): void {
    this.pendingDeleteLink = null;
    this.isDeleteLinkModalOpen = false;
  }

  confirmDeleteLinkRemoval(): void {
    if (!this.selectedDocument || !this.pendingDeleteLink) {
      this.cancelDeleteLinkRemoval();
      return;
    }

    const documentId = this.selectedDocument.id;
    const linkId = this.pendingDeleteLink.id;

    this.linksSaving = true;
    this.clearMessages();

    this.internalDocumentsService.deleteDocumentLink(documentId, linkId).subscribe({
      next: (response) => {
        this.linksSaving = false;
        this.successMessage = response.message || 'Vínculo documental desactivado.';
        this.cancelDeleteLinkRemoval();
        this.reloadSelectedDocumentDetails(documentId);
      },
      error: (error) => {
        this.linksSaving = false;
        this.errorMessage = this.resolveErrorMessage(
          error,
          'No se pudo desactivar el vínculo documental.'
        );
      },
    });
  }

  openAssignDocumentModal(document: InternalDocument): void {
    this.clearMessages();
    this.selectDocument(document);
    this.isAssignDocumentModalOpen = true;
  }

  closeAssignDocumentModal(): void {
    if (this.linksSaving) {
      return;
    }

    this.isAssignDocumentModalOpen = false;
  }

  openReplaceVersionModal(document: InternalDocument): void {
    this.clearMessages();
    this.selectDocument(document);
    this.versionFile = null;
    this.versionForm = {
      version_label: '',
      change_notes: '',
    };
    this.isReplaceVersionModalOpen = true;
  }

  closeReplaceVersionModal(): void {
    if (this.saving) {
      return;
    }

    this.isReplaceVersionModalOpen = false;
    this.versionFile = null;
    this.versionForm = {
      version_label: '',
      change_notes: '',
    };
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
    this.previewExternalResource = null;

    if (clearError) {
      this.previewErrorMessage = '';
    }
  }

getDocumentPrimaryExternalResource(
  document: InternalDocument
): InternalDocumentExternalResource | null {
  if (document.primary_external_resource) {
    return document.primary_external_resource;
  }

  if (this.selectedDocument?.id === document.id) {
    return this.getPrimaryExternalResource();
  }

  return null;
}

canPreviewDocumentVideo(document: InternalDocument): boolean {
  const resource = this.getDocumentPrimaryExternalResource(document);

  return Boolean(
    document.has_external_resources &&
    resource &&
    resource.resource_kind === 'VIDEO' &&
    resource.preview_url
  );
}

openDocumentVideo(document: InternalDocument): void {
  const resource = this.getDocumentPrimaryExternalResource(document);

  if (!resource) {
    this.errorMessage = 'Este documento no tiene video disponible.';
    return;
  }

  this.openExternalResourcePreview(resource);
}

  canPreviewDocument(document: InternalDocument): boolean {
    return this.canDownload(document) && this.resolvePreviewType(document) !== null;
  }

  canManageLinks(document: InternalDocument | null): boolean {
    return this.canManage &&
      Boolean(document?.capabilities?.can_edit) &&
      document?.status !== 'ARCHIVADO';
  }

  getSelectedDocumentLinks(): InternalDocumentLink[] {
    return this.selectedDocument?.links || [];
  }

  getEntityTypeLabel(entityType: string | null | undefined): string {
    return this.linkEntityTypeOptions.find((item) => item.value === entityType)?.label ||
      entityType ||
      'Sin entidad';
  }

  getLinkRoleLabel(linkRole: string | null | undefined): string {
    return this.linkRoleOptions.find((item) => item.value === linkRole)?.label ||
      linkRole ||
      'Sin rol';
  }

  getLinkContextLabel(link: InternalDocumentLink): string {
    if (link.entity_key) {
      return link.entity_key;
    }

    if (link.entity_id) {
      return `ID ${link.entity_id}`;
    }

    return 'GENERAL';
  }

  isGeneralLinkEntitySelected(): boolean {
    return this.linkForm.entity_type === 'GENERAL';
  }

  canCreateLinkForSelectedDocument(): boolean {
    if (!this.canManageLinks(this.selectedDocument) || this.linksSaving) {
      return false;
    }

    if (!this.linkForm.entity_type || !this.linkForm.link_role) {
      return false;
    }

    if (this.linkForm.entity_type === 'GENERAL') {
      return true;
    }

    const entityKey = this.linkForm.entity_key.trim();

    return Boolean(entityKey || this.linkForm.entity_id);
  }

  getLinkContextFieldLabel(): string {
    const labels: Record<InternalDocumentLinkEntityType, string> = {
      OPENING: 'Apertura',
      PROJECT: 'Proyecto',
      TASK: 'Tarea',
      SUCURSAL: 'Sucursal',
      DEPARTMENT: 'Departamento / Área',
      GENERAL: 'Contexto general',
    };

    return labels[this.linkForm.entity_type] || 'Contexto';
  }

  getLinkContextPlaceholder(): string {
    const placeholders: Record<InternalDocumentLinkEntityType, string> = {
      OPENING: 'Ej. EGADE o SERRANIA',
      PROJECT: 'Ej. PROYECTO_EGADE',
      TASK: 'Ej. EGADE-ELECTRICO-001',
      SUCURSAL: 'Ej. INSURGENTES',
      DEPARTMENT: 'Ej. SISTEMAS',
      GENERAL: 'GENERAL',
    };

    return placeholders[this.linkForm.entity_type] || 'Ej. EGADE';
  }

  getLinkContextHelpText(): string {
    if (this.linkForm.entity_type === 'GENERAL') {
      return 'Para contexto general se usará GENERAL automáticamente si lo dejas vacío.';
    }

    return 'Campo requerido. Usa una clave fácil de reconocer, por ejemplo EGADE, SERRANIA o INSURGENTES.';
  }

  shouldShowLinkContextRequiredHint(): boolean {
    if (this.linkForm.entity_type === 'GENERAL') {
      return false;
    }

    return !this.linkForm.entity_key.trim() && !this.linkForm.entity_id;
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

  isCustomPeriodSelected(): boolean {
    return this.filters.period === 'custom';
  }

  getPeriodLabel(period: string | null | undefined = this.filters.period): string {
    const option = this.periodOptions.find((item) => item.value === period);
    return option?.label || 'Hoy';
  }

  getLibraryContextLabel(): string {
    const totalLabel = `${this.total} documento${this.total === 1 ? '' : 's'}`;

    if (this.filters.period === 'custom') {
      const from = this.filters.date_from || 'inicio';
      const to = this.filters.date_to || 'fin';

      return `Personalizado · ${from} a ${to} · ${totalLabel}`;
    }

    return `${this.getPeriodLabel()} · ${totalLabel}`;
  }

  getPaginationRangeLabel(): string {
    if (!this.total) {
      return '0 documentos';
    }

    const start = ((this.page || 1) - 1) * this.pageSize + 1;
    const end = Math.min(start + this.documents.length - 1, this.total);

    return `${start}-${end} de ${this.total} documentos`;
  }

  getHeroDescription(): string {
    if (this.canManage) {
      return 'Documentos publicados, manuales, reportes, políticas, formatos y evidencia operativa con control de versión, permisos y trazabilidad.';
    }

    return 'Consulta y descarga documentos corporativos disponibles para tu operación.';
  }

  getLibraryTitle(): string {
    return this.canManage ? 'Explorar documentos' : 'Buscar documentos';
  }

  getEmptyStateTitle(): string {
    return this.canManage
      ? 'No hay documentos para mostrar'
      : 'No encontramos documentos disponibles';
  }

  getEmptyStateDescription(): string {
    return this.canManage
      ? 'Prueba limpiar filtros o crear un nuevo documento.'
      : 'Prueba cambiar el periodo, la categoría o el texto de búsqueda.';
  }

  getDetailPanelTitle(): string {
    return this.canManage ? 'Ficha documental' : 'Documento disponible';
  }

  getDetailPanelEmptyTitle(): string {
    return this.canManage ? 'Selecciona un documento' : 'Elige un documento';
  }

  getDetailPanelEmptyDescription(): string {
    return this.canManage
      ? 'El detalle, vista previa, descarga y contexto documental aparecerán aquí.'
      : 'Aquí podrás ver el resumen y descargar el archivo seleccionado.';
  }

  shouldShowAdminMetadata(): boolean {
    return this.canManage;
  }

  shouldShowDocumentStatus(document: InternalDocument): boolean {
    return this.canManage || document.status !== 'PUBLICADO';
  }

  shouldShowDocumentVisibility(): boolean {
    return this.canManage;
  }

  shouldShowSensitiveChip(document: InternalDocument): boolean {
    return this.canManage && Boolean(document.is_sensitive);
  }

  shouldShowVersionLabel(): boolean {
    return this.canManage;
  }

  shouldShowOwnerLabel(): boolean {
    return this.canManage;
  }

  shouldShowLinksPanel(document: InternalDocument | null): boolean {
    return this.canManageLinks(document);
  }

  shouldShowVersionPanel(document: InternalDocument | null): boolean {
    if (!document) {
      return false;
    }

    return this.canReplaceVersion(document);
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

  getDocumentInitial(document: InternalDocument): string {
    const title = (document.title || 'D').trim();

    return title.charAt(0).toUpperCase() || 'D';
  }

  getFileTypeLabel(document: InternalDocument): string {
    const filename = String(document.current_version?.original_filename || '').trim();
    const extension = filename.includes('.')
      ? filename.split('.').pop()
      : '';

    if (extension) {
      return extension.toUpperCase();
    }

    const mimeType = String(document.current_version?.file_mime_type || '').toLowerCase();

    if (mimeType.includes('pdf')) {
      return 'PDF';
    }

    if (mimeType.includes('image')) {
      return 'IMG';
    }

    if (mimeType.includes('spreadsheet') || mimeType.includes('excel')) {
      return 'XLSX';
    }

    if (mimeType.includes('word')) {
      return 'DOCX';
    }

    if (mimeType.includes('presentation')) {
      return 'PPTX';
    }

    return 'DOC';
  }

  getSelectedDocumentFilename(): string {
    return this.selectedDocument?.current_version?.original_filename || 'Sin archivo';
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

hasCreateDocumentOwner(): boolean {
  return Boolean(this.form.owner_user_id || this.form.owner_department_id);
}

hasCreateDescription(): boolean {
  return Boolean(this.form.description.trim());
}

hasValidOptionalExternalResourceData(): boolean {
  const originalUrl = this.externalResourceForm.original_url.trim();
  const title = this.externalResourceForm.title.trim();
  const description = this.externalResourceForm.description.trim();

  if (!title && !description) {
    return true;
  }

  return Boolean(originalUrl);
}

canCreateDraft(): boolean {
  return !this.saving &&
    Boolean(this.selectedFile) &&
    Boolean(this.form.title.trim()) &&
    Boolean(this.form.category_id) &&
    this.hasCreateDescription() &&
    this.hasCreateDocumentOwner() &&
    this.hasValidOptionalExternalResourceData();
}

shouldShowCreateDescriptionRequiredHint(): boolean {
  return !this.hasCreateDescription();
}

shouldShowCreateOwnerRequiredHint(): boolean {
  return !this.hasCreateDocumentOwner();
}

shouldShowCreateVideoUrlRequiredHint(): boolean {
  const originalUrl = this.externalResourceForm.original_url.trim();
  const title = this.externalResourceForm.title.trim();
  const description = this.externalResourceForm.description.trim();

  return !originalUrl && Boolean(title || description);
}

hasPublishRequirements(document: InternalDocument): boolean {
  return Boolean(
    document.description?.trim() &&
    (document.owner_user_id || document.owner_department_id)
  );
}

getPublishRequirementsMessage(document: InternalDocument): string {
  const missing: string[] = [];

  if (!document.description?.trim()) {
    missing.push('descripción');
  }

  if (!document.owner_user_id && !document.owner_department_id) {
    missing.push('dueño documental');
  }

  if (!missing.length) {
    return '';
  }

  return `Para publicar falta: ${missing.join(' y ')}.`;
}

  canReplaceVersion(document: InternalDocument): boolean {
    return this.canManage &&
      Boolean(document?.capabilities?.can_replace_version) &&
      document.status !== 'ARCHIVADO';
  }
  canDownload(document: InternalDocument): boolean {
    return Boolean(document?.capabilities?.can_download);
  }

  trackByDocumentId(_index: number, document: InternalDocument): number {
    return document.id;
  }

  hasExternalResources(): boolean {
    return this.externalResources.length > 0;
  }  

  getPrimaryExternalResource(): InternalDocumentExternalResource | null {
  return this.externalResources.find((resource) => resource.is_primary) ||
    this.externalResources[0] ||
    null;
}

getExternalResourceTitle(resource: InternalDocumentExternalResource): string {
  return resource.title || 'Video de Google Drive';
}

canPreviewExternalResource(resource: InternalDocumentExternalResource): boolean {
  return Boolean(resource.preview_url && resource.resource_kind === 'VIDEO');
}

openExternalResourcePreview(resource: InternalDocumentExternalResource): void {
  if (!resource.preview_url) {
    this.errorMessage = 'Este video no tiene URL de vista previa.';
    return;
  }

  this.clearMessages();
  this.closePreview(false);

  this.previewOpen = true;
  this.previewLoading = false;
  this.previewErrorMessage = '';
  this.previewTitle = this.getExternalResourceTitle(resource);
  this.previewType = 'drive-video';
  this.previewDocument = null;
  this.previewExternalResource = resource;
  this.previewSafeUrl = this.sanitizer.bypassSecurityTrustResourceUrl(
    resource.preview_url
  );
}

createExternalResourceForSelectedDocument(): void {
  if (!this.canManage || !this.selectedDocument) {
    return;
  }

  const payload = this.buildExternalResourcePayload();

  if (!payload) {
    return;
  }

  this.externalResourcesSaving = true;
  this.clearMessages();

  this.internalDocumentsService.createExternalResource(
    this.selectedDocument.id,
    payload
  ).subscribe({
    next: (response) => {
      this.externalResourcesSaving = false;
      this.successMessage = response.message || 'Recurso externo creado.';
      this.resetExternalResourceForm();
      this.loadExternalResourcesForSelectedDocument();
    },
    error: (error) => {
      this.externalResourcesSaving = false;
      this.errorMessage = this.resolveErrorMessage(
        error,
        'No se pudo crear el recurso externo.'
      );
    },
  });
}

  private updateVisibleDocumentSummary(): void {
    this.visiblePublishedCount = this.documents.filter(
      (document) => document.status === 'PUBLICADO'
    ).length;

    this.visibleDraftCount = this.documents.filter(
      (document) => document.status === 'BORRADOR'
    ).length;

    this.visibleSensitiveCount = this.documents.filter(
      (document) => Boolean(document.is_sensitive)
    ).length;

    this.visiblePreviewableCount = this.documents.filter(
      (document) => this.canPreviewDocument(document)
    ).length;
  }

  private applyDocumentUpdateToCurrentList(updatedDocument: InternalDocument): void {
    this.documents = this.documents.map((document) =>
      document.id === updatedDocument.id ? updatedDocument : document
    );

    if (this.selectedDocument?.id === updatedDocument.id) {
      this.selectedDocument = updatedDocument;
    }

    this.updateVisibleDocumentSummary();
  }

  private buildLinkPayload(): InternalDocumentLinkPayload | null {
    const entityKey = this.linkForm.entity_key.trim();
    const label = this.linkForm.label.trim();

    if (!this.linkForm.entity_type) {
      this.errorMessage = 'Selecciona el tipo de entidad.';
      return null;
    }

    if (!this.linkForm.link_role) {
      this.errorMessage = 'Selecciona el rol documental.';
      return null;
    }

    if (
      this.linkForm.entity_type !== 'GENERAL' &&
      !entityKey &&
      !this.linkForm.entity_id
    ) {
      this.errorMessage = 'Captura entity key o entity id para vincular el documento.';
      return null;
    }

    const payload: InternalDocumentLinkPayload = {
      entity_type: this.linkForm.entity_type,
      link_role: this.linkForm.link_role,
      entity_key: entityKey || null,
      entity_id: this.linkForm.entity_id,
      label: label || null,
      is_primary: this.linkForm.is_primary,
    };

    if (this.linkForm.entity_type === 'GENERAL') {
      payload.entity_id = null;
      payload.entity_key = entityKey || 'GENERAL';
    }

    return payload;
  }

private buildExternalResourcePayload(
  options: { requireUrl?: boolean } = {}
): InternalDocumentExternalResourcePayload | null {
  const requireUrl = options.requireUrl ?? true;

  const originalUrl = this.externalResourceForm.original_url.trim();
  const title = this.externalResourceForm.title.trim();
  const description = this.externalResourceForm.description.trim();

  const hasAnyResourceData = Boolean(originalUrl || title || description);

  if (!originalUrl) {
    if (!requireUrl && !hasAnyResourceData) {
      return null;
    }

    this.errorMessage = 'Captura el link de Google Drive para registrar el video.';
    return null;
  }

  return {
    provider: 'GOOGLE_DRIVE',
    resource_kind: 'VIDEO',
    original_url: originalUrl,
    title: title || null,
    description: description || null,
    is_primary: this.externalResourceForm.is_primary,
  };
}

  private resetLinkForm(): void {
    this.linkForm = {
      entity_type: 'OPENING',
      entity_id: null,
      entity_key: '',
      link_role: 'MANUAL',
      label: '',
      is_primary: false,
    };
  }

private resetExternalResourceForm(): void {
  this.externalResourceForm = {
    original_url: '',
    title: '',
    description: '',
    is_primary: true,
  };
}

  private reloadSelectedDocumentDetails(documentId: number): void {
    this.internalDocumentsService.getDocument(documentId).subscribe({
      next: (item) => {
        this.selectedDocument = item;
      },
      error: () => {
        this.errorMessage = 'No se pudo recargar el detalle del documento.';
      },
    });
  }

  loadExternalResourcesForSelectedDocument(): void {
    const document = this.selectedDocument;

    if (!document) {
      this.externalResources = [];
      return;
    }

    this.externalResourcesLoading = true;

    this.internalDocumentsService.getExternalResources(document.id).subscribe({
      next: (response) => {
        this.externalResources = response.items || [];
        this.externalResourcesLoading = false;
      },
      error: () => {
        this.externalResources = [];
        this.externalResourcesLoading = false;
        this.errorMessage = 'No se pudieron cargar los recursos externos del documento.';
      },
    });
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

  private scheduleSearchReload(): void {
    this.cancelScheduledSearchReload();

    this.searchDebounceTimer = setTimeout(() => {
      this.searchDebounceTimer = null;
      this.resetListCache();
      this.loadDocuments();
    }, this.searchDebounceMs);
  }

  private cancelScheduledSearchReload(): void {
    if (!this.searchDebounceTimer) {
      return;
    }

    clearTimeout(this.searchDebounceTimer);
    this.searchDebounceTimer = null;
  }

  private getEffectivePeriod(): InternalDocumentPeriodFilter {
    const cleanSearch = (this.filters.q || '').trim();

    if (cleanSearch && this.searchForcedAllPeriod) {
      return 'all';
    }

    return this.filters.period || 'today';
  }

  private buildFilters(): InternalDocumentListFilters {
    const cleanSearch = (this.filters.q || '').trim();
    const hasSearch = cleanSearch.length > 0;
    const effectivePeriod = this.getEffectivePeriod();

    const page = this.filters.page || 1;
    const pageSize = this.visiblePageSize;
    const offset = this.getRequestOffsetForPage(page);
    const limit = this.getRequestLimit();

    return {
      q: cleanSearch,
      category_id: this.filters.category_id || null,
      status: this.canManage ? (this.filters.status || 'ALL') : null,
      owner_department_id: this.filters.owner_department_id || null,
      is_sensitive: this.filters.is_sensitive ?? null,
      period: effectivePeriod,
      date_from: hasSearch ? null : (this.filters.date_from || null),
      date_to: hasSearch ? null : (this.filters.date_to || null),
      page,
      page_size: pageSize,
      offset,
      limit,
    };
  }

  private getRequestOffsetForPage(page: number): number {
    const pageOffset = Math.max(page - 1, 0) * this.visiblePageSize;

    if (this.getEffectivePeriod() === 'all') {
      return Math.floor(pageOffset / this.allPeriodBlockSize) * this.allPeriodBlockSize;
    }

    return pageOffset;
  }

  private getRequestLimit(): number {
    return this.getEffectivePeriod() === 'all'
      ? this.allPeriodBlockSize
      : this.visiblePageSize;
  }

  private buildListSignature(filters: InternalDocumentListFilters): string {
    return JSON.stringify({
      q: filters.q || '',
      category_id: filters.category_id || null,
      status: filters.status || null,
      owner_department_id: filters.owner_department_id || null,
      is_sensitive: filters.is_sensitive ?? null,
      period: filters.period || 'today',
      date_from: filters.date_from || null,
      date_to: filters.date_to || null,
    });
  }

  private canUseCachedBlock(signature: string, requestedOffset: number): boolean {
    if (!this.cachedBlockItems.length) {
      return false;
    }

    if (this.cachedBlockSignature !== signature) {
      return false;
    }

    const pageOffset = Math.max((this.filters.page || 1) - 1, 0) * this.visiblePageSize;
    const cachedStart = this.cachedBlockOffset;
    const cachedEnd = this.cachedBlockOffset + this.cachedBlockItems.length;

    return pageOffset >= cachedStart && pageOffset < cachedEnd;
  }

  private applyCachedBlock(requestedOffset: number): void {
    this.applyResponseBlock(
      this.cachedBlockItems,
      this.cachedBlockOffset,
      {
        items: this.cachedBlockItems,
        page: this.filters.page || 1,
        page_size: this.visiblePageSize,
        total: this.cachedBlockTotal,
        total_pages: this.cachedBlockTotalPages,
        has_next: (this.filters.page || 1) < this.cachedBlockTotalPages,
        has_prev: (this.filters.page || 1) > 1,
        offset: requestedOffset,
        limit: this.getRequestLimit(),
        returned: this.cachedBlockItems.length,
        has_more: false,
        next_offset: null,
        period: this.getEffectivePeriod(),
        date_from: this.filters.date_from || null,
        date_to: this.filters.date_to || null,
      } as InternalDocumentListResponse
    );

    this.refreshSelectedDocumentFromCurrentPage();
  }

  private applyResponseBlock(
    blockItems: InternalDocument[],
    blockOffset: number,
    response: InternalDocumentListResponse
  ): void {
    this.page = this.filters.page || response.page || 1;
    this.pageSize = this.visiblePageSize;
    this.total = response.total || 0;
    this.totalPages = response.total_pages || 0;

    const pageOffset = Math.max(this.page - 1, 0) * this.visiblePageSize;
    const startWithinBlock = Math.max(pageOffset - blockOffset, 0);

    this.documents = blockItems.slice(
      startWithinBlock,
      startWithinBlock + this.visiblePageSize
    );

    this.hasPrev = this.page > 1;
    this.hasNext = this.page < (this.totalPages || 0);

    this.updateVisibleDocumentSummary();
  }

  private refreshSelectedDocumentFromCurrentPage(): void {
    if (!this.selectedDocument) {
      return;
    }

    const refreshed = this.documents.find(
      (item) => item.id === this.selectedDocument?.id
    );

    if (!refreshed) {
      return;
    }

    this.selectedDocument = {
      ...this.selectedDocument,
      ...refreshed,
      links: this.selectedDocument.links,
      visibility_rules: this.selectedDocument.visibility_rules,
    };
  }

  private resetListCache(): void {
    this.cachedBlockSignature = '';
    this.cachedBlockOffset = -1;
    this.cachedBlockItems = [];
    this.cachedBlockTotal = 0;
    this.cachedBlockTotalPages = 0;
  }

  private resetCreateForm(): void {
    this.selectedFile = null;
    this.form = {
      title: '',
      description: '',
      category_id: this.categories[0]?.id || null,
      document_type: '',
      owner_user_id: this.currentUserId,
      owner_department_id: null,
      is_sensitive: false,
      version_label: '1.0',
      change_notes: 'Versión inicial',
    };

    this.resetExternalResourceForm();
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