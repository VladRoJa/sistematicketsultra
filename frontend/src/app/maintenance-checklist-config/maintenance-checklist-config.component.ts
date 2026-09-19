import { CommonModule } from '@angular/common';
import { Component, OnInit, inject } from '@angular/core';
import { FormsModule } from '@angular/forms';

import {
  MaintenanceChecklistCatalog,
  MaintenanceChecklistItem,
  MaintenanceChecklistTemplate,
  MaintenancePreventiveService,
  MaintenanceReprogramReason,
} from '../services/maintenance-preventive.service';

@Component({
  selector: 'app-maintenance-checklist-config',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './maintenance-checklist-config.component.html',
  styleUrls: ['./maintenance-checklist-config.component.css'],
})
export class MaintenanceChecklistConfigComponent implements OnInit {
  private readonly service = inject(MaintenancePreventiveService);

  catalog: MaintenanceChecklistCatalog = {
    templates: [],
    families: [],
  };

  familyId: number | null = null;
  templateName = '';
  activity = '';
  initialItemsText = '';

  newItemByTemplate: Record<number, string> = {};

  reprogramReasons: MaintenanceReprogramReason[] = [];
  newReasonKey = '';
  newReasonName = '';
  newReasonRequiresComment = false;
  newReasonOrder = 0;

  loading = false;
  saving = false;
  errorMessage = '';
  successMessage = '';

  ngOnInit(): void {
    this.loadCatalog();
    this.loadReprogramReasons();
  }

  loadCatalog(): void {
    this.loading = true;
    this.clearMessages();

    this.service.getChecklistCatalog().subscribe({
      next: (catalog) => {
        this.catalog = catalog;
        this.loading = false;
      },
      error: (error) => {
        this.loading = false;
        this.setError(error, 'No se pudieron cargar los checklists.');
      },
    });
  }

  loadReprogramReasons(): void {
    this.service.getReprogramReasons(true).subscribe({
      next: (response) => {
        this.reprogramReasons = response.reasons || [];
      },
      error: (error) => {
        this.setError(
          error,
          'No se pudieron cargar los motivos de reprogramación.',
        );
      },
    });
  }

  createReprogramReason(): void {
    if (!this.newReasonKey.trim() || !this.newReasonName.trim()) {
      this.errorMessage = 'Escribe key y nombre del motivo.';
      return;
    }

    this.saving = true;
    this.clearMessages();

    this.service.createReprogramReason({
      key: this.newReasonKey.trim(),
      nombre: this.newReasonName.trim(),
      requiere_comentario: this.newReasonRequiresComment,
      orden: this.newReasonOrder,
    }).subscribe({
      next: () => {
        this.saving = false;
        this.newReasonKey = '';
        this.newReasonName = '';
        this.newReasonRequiresComment = false;
        this.newReasonOrder = 0;
        this.successMessage = 'Motivo creado.';
        this.loadReprogramReasons();
      },
      error: (error) => {
        this.saving = false;
        this.setError(error, 'No se pudo crear el motivo.');
      },
    });
  }

  saveReprogramReason(reason: MaintenanceReprogramReason): void {
    this.saving = true;
    this.clearMessages();

    this.service.updateReprogramReason(reason.id, {
      nombre: reason.nombre,
      requiere_comentario: reason.requiere_comentario,
      activo: reason.activo,
      orden: reason.orden,
    }).subscribe({
      next: () => {
        this.saving = false;
        this.successMessage = 'Motivo actualizado.';
        this.loadReprogramReasons();
      },
      error: (error) => {
        this.saving = false;
        this.setError(error, 'No se pudo actualizar el motivo.');
      },
    });
  }

  trackReason(_: number, reason: MaintenanceReprogramReason): number {
    return reason.id;
  }

  createTemplate(): void {
    if (!this.familyId || !this.templateName.trim()) {
      this.errorMessage = 'Selecciona familia y escribe un nombre.';
      return;
    }

    const items = this.initialItemsText
      .split(/\r?\n/)
      .map((value) => value.trim())
      .filter(Boolean)
      .map((etiqueta) => ({ etiqueta, requerido: true }));

    this.saving = true;
    this.clearMessages();

    this.service.createChecklist({
      familia_equipo_id: this.familyId,
      nombre: this.templateName.trim(),
      actividad: this.activity.trim() || null,
      items,
    }).subscribe({
      next: () => {
        this.saving = false;
        this.templateName = '';
        this.activity = '';
        this.initialItemsText = '';
        this.successMessage = 'Checklist creado.';
        this.loadCatalog();
      },
      error: (error) => {
        this.saving = false;
        this.setError(error, 'No se pudo crear el checklist.');
      },
    });
  }

  saveTemplate(template: MaintenanceChecklistTemplate): void {
    this.saving = true;
    this.clearMessages();

    this.service.updateChecklist(template.id, {
      nombre: template.nombre,
      actividad: template.actividad,
      activo: template.activo,
    }).subscribe({
      next: () => {
        this.saving = false;
        this.successMessage = 'Checklist actualizado.';
        this.loadCatalog();
      },
      error: (error) => {
        this.saving = false;
        this.setError(error, 'No se pudo actualizar el checklist.');
      },
    });
  }

  addItem(template: MaintenanceChecklistTemplate): void {
    const label = (this.newItemByTemplate[template.id] || '').trim();
    if (!label) {
      this.errorMessage = 'Escribe la etiqueta del nuevo ítem.';
      return;
    }

    this.saving = true;
    this.clearMessages();

    this.service.addChecklistItem(template.id, {
      etiqueta: label,
      requerido: true,
    }).subscribe({
      next: () => {
        this.saving = false;
        this.newItemByTemplate[template.id] = '';
        this.successMessage = 'Ítem agregado.';
        this.loadCatalog();
      },
      error: (error) => {
        this.saving = false;
        this.setError(error, 'No se pudo agregar el ítem.');
      },
    });
  }

  saveItem(
    template: MaintenanceChecklistTemplate,
    item: MaintenanceChecklistItem,
  ): void {
    this.saving = true;
    this.clearMessages();

    this.service.updateChecklistItem(
      template.id,
      item.id,
      {
        etiqueta: item.etiqueta,
        orden: item.orden,
        requerido: item.requerido,
        activo: item.activo ?? true,
      },
    ).subscribe({
      next: () => {
        this.saving = false;
        this.successMessage = 'Ítem actualizado.';
        this.loadCatalog();
      },
      error: (error) => {
        this.saving = false;
        this.setError(error, 'No se pudo actualizar el ítem.');
      },
    });
  }

  trackTemplate(_: number, template: MaintenanceChecklistTemplate): number {
    return template.id;
  }

  trackItem(_: number, item: MaintenanceChecklistItem): number {
    return item.id;
  }

  private clearMessages(): void {
    this.errorMessage = '';
    this.successMessage = '';
  }

  private setError(error: any, fallback: string): void {
    this.errorMessage =
      error?.error?.mensaje
      || error?.error?.detail
      || error?.message
      || fallback;
  }
}
