import { CommonModule } from '@angular/common';
import { Component, OnInit, inject } from '@angular/core';
import { FormsModule } from '@angular/forms';

import {
  MaintenanceCrew,
  MaintenancePersonnel,
  MaintenancePersonnelCatalog,
  MaintenancePreventiveService,
} from '../services/maintenance-preventive.service';

@Component({
  selector: 'app-maintenance-crew-config',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './maintenance-crew-config.component.html',
  styleUrls: ['./maintenance-crew-config.component.css'],
})
export class MaintenanceCrewConfigComponent implements OnInit {
  private readonly service = inject(MaintenancePreventiveService);

  catalog: MaintenancePersonnelCatalog = {
    personnel: [],
    candidates: [],
    crews: [],
    regions: [],
  };

  newCrewName = '';
  newCrewRegionId: number | null = null;
  newPersonnelUserId: number | null = null;
  newPersonnelCrewId: number | null = null;

  loading = false;
  saving = false;
  errorMessage = '';
  successMessage = '';

  ngOnInit(): void {
    this.loadCatalog();
  }

  get availableCandidates() {
    const assigned = new Set(
      this.catalog.personnel.map((row) => row.user_id),
    );
    return this.catalog.candidates.filter(
      (candidate) => !assigned.has(candidate.user_id),
    );
  }

  loadCatalog(): void {
    this.loading = true;
    this.clearMessages();

    this.service.getPersonnelCatalog().subscribe({
      next: (catalog) => {
        this.catalog = catalog;
        this.loading = false;
      },
      error: (error) => {
        this.loading = false;
        this.setError(error, 'No se pudo cargar el catálogo de Mantenimiento.');
      },
    });
  }

  createCrew(): void {
    const name = this.newCrewName.trim();
    if (!name) {
      this.errorMessage = 'Escribe un nombre para la cuadrilla.';
      return;
    }

    this.saving = true;
    this.clearMessages();

    this.service.createCrew({
      nombre: name,
      region_id: this.newCrewRegionId,
    }).subscribe({
      next: () => {
        this.saving = false;
        this.newCrewName = '';
        this.newCrewRegionId = null;
        this.successMessage = 'Cuadrilla creada.';
        this.loadCatalog();
      },
      error: (error) => {
        this.saving = false;
        this.setError(error, 'No se pudo crear la cuadrilla.');
      },
    });
  }

  saveCrew(crew: MaintenanceCrew): void {
    this.saving = true;
    this.clearMessages();

    this.service.updateCrew(crew.id, {
      nombre: crew.nombre,
      region_id: crew.region_id,
      activo: crew.activo,
    }).subscribe({
      next: () => {
        this.saving = false;
        this.successMessage = 'Cuadrilla actualizada.';
        this.loadCatalog();
      },
      error: (error) => {
        this.saving = false;
        this.setError(error, 'No se pudo actualizar la cuadrilla.');
      },
    });
  }

  createPersonnel(): void {
    if (!this.newPersonnelUserId) {
      this.errorMessage = 'Selecciona un usuario de Mantenimiento.';
      return;
    }

    this.saving = true;
    this.clearMessages();

    this.service.createPersonnel({
      user_id: this.newPersonnelUserId,
      crew_id: this.newPersonnelCrewId,
    }).subscribe({
      next: () => {
        this.saving = false;
        this.newPersonnelUserId = null;
        this.newPersonnelCrewId = null;
        this.successMessage = 'Personal agregado al catálogo.';
        this.loadCatalog();
      },
      error: (error) => {
        this.saving = false;
        this.setError(error, 'No se pudo agregar el personal.');
      },
    });
  }

  savePersonnel(row: MaintenancePersonnel): void {
    this.saving = true;
    this.clearMessages();

    this.service.updatePersonnel(row.id, {
      crew_id: row.crew_id,
      activo: row.activo,
    }).subscribe({
      next: () => {
        this.saving = false;
        this.successMessage = 'Personal actualizado.';
        this.loadCatalog();
      },
      error: (error) => {
        this.saving = false;
        this.setError(error, 'No se pudo actualizar el personal.');
      },
    });
  }

  trackCrew(_: number, row: MaintenanceCrew): number {
    return row.id;
  }

  trackPersonnel(_: number, row: MaintenancePersonnel): number {
    return row.id;
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
