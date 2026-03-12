// frontend/src/app/pm/pm-calendario/pm-calendario.component.ts


import { Component, OnInit, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { PmPreventivoService } from '../../services/pm-preventivo.service';
import { PmConfiguracionResumen, SucursalOption  } from '../../models/pm-preventivo.model';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatSelectModule } from '@angular/material/select';


import {
  generarSemanasDelMes,
  SemanaCalendarioPmOption,
} from '../helpers/calendario-pm.helper';

@Component({
  selector: 'app-pm-calendario',
  standalone: true,
  imports: [CommonModule,
            FormsModule,
            MatFormFieldModule,
            MatSelectModule,
  ],
  templateUrl: './pm-calendario.component.html',
  styleUrls: ['./pm-calendario.component.css'],
})
export class PmCalendarioComponent implements OnInit {

    private pmService = inject(PmPreventivoService);

  anioSeleccionado = 2026;
  mesSeleccionado = 6;
  semanaSeleccionada: number | null = null;

  semanasDisponibles: SemanaCalendarioPmOption[] = [];

  sucursalesCalendario: SucursalOption[] = [];
  sucursalesSeleccionadasIds: number[] = [];
  mostrarTodasLasSucursales = true;
  valorSeleccionSucursales: number[] = [-1];
  configuracionesPm: PmConfiguracionResumen[] = [];
  calendarioPmData: any = null;
  detalleSemanaSeleccionada: any = null;

  ngOnInit(): void {
    this.cargarSucursalesCalendario();
    this.actualizarSemanasDisponibles();
    this.cargarCalendarioPm();
  }

    actualizarSemanasDisponibles(): void {
    this.semanasDisponibles = generarSemanasDelMes(
        this.anioSeleccionado,
        this.mesSeleccionado
    );

    this.semanaSeleccionada = this.semanasDisponibles[0]?.semana_anio ?? null;
    this.cargarCalendarioPm();
    }

  get semanaSeleccionadaInfo(): SemanaCalendarioPmOption | null {
    return (
        this.semanasDisponibles.find(
        (semana) => semana.semana_anio === this.semanaSeleccionada
        ) || null
    );
    }   

cargarSucursalesCalendario(): void {
  this.pmService.getSucursalesPermitidas().subscribe({
    next: (rows) => {
      this.sucursalesCalendario = rows || [];
    },
    error: () => {
      this.sucursalesCalendario = [];
    },
  });
}

obtenerGridTemplateColumns(): string {
  const totalSemanas = this.semanasDisponibles.length;

  if (!totalSemanas) {
    return '220px';
  }

  return `220px repeat(${totalSemanas}, minmax(210px, 1fr))`;
}

get sucursalesCalendarioFiltradas(): SucursalOption[] {
  if (
    this.mostrarTodasLasSucursales ||
    this.sucursalesSeleccionadasIds.length === 0 ||
    this.sucursalesSeleccionadasIds.includes(-1)
  ) {
    return this.sucursalesCalendario;
  }

  return this.sucursalesCalendario.filter((sucursal) =>
    this.sucursalesSeleccionadasIds.includes(sucursal.sucursal_id)
  );
}

manejarCambioSucursalesSeleccionadas(valores: number[]): void {
  const valoresActuales = this.sucursalesSeleccionadasIds;

  if (!valores || valores.length === 0) {
    this.mostrarTodasLasSucursales = false;
    this.sucursalesSeleccionadasIds = [];
    this.cargarCalendarioPm();
    return;
  }

  const incluyeTodas = valores.includes(-1);
  const antesIncluiaTodas = valoresActuales.includes(-1);

  if (incluyeTodas && !antesIncluiaTodas) {
    this.mostrarTodasLasSucursales = true;
    this.sucursalesSeleccionadasIds = [-1];
    this.cargarCalendarioPm();
    return;
  }

  if (incluyeTodas && valores.length > 1) {
    const idsValidos = valores.filter((id) => id !== -1);
    this.mostrarTodasLasSucursales = false;
    this.sucursalesSeleccionadasIds = idsValidos;
    this.cargarCalendarioPm();
    return;
  }

  if (incluyeTodas) {
    this.mostrarTodasLasSucursales = true;
    this.sucursalesSeleccionadasIds = [-1];
    this.cargarCalendarioPm();
    return;
  }

  this.mostrarTodasLasSucursales = false;
  this.sucursalesSeleccionadasIds = valores.filter((id) => id !== -1);
  this.cargarCalendarioPm();
}

cargarConfiguracionesPm(): void {
  this.pmService.listarConfiguracionesPm().subscribe({
    next: (rows) => {
      this.configuracionesPm = rows || [];
    },
    error: () => {
      this.configuracionesPm = [];
    },
  });
}

obtenerTotalConfiguracionesSucursal(sucursalId: number): number {
  return this.configuracionesPm.filter(
    (config) => config.sucursal_id === sucursalId
  ).length;
}


cargarCalendarioPm(): void {
  const sucursalesIds =
    this.mostrarTodasLasSucursales || this.sucursalesSeleccionadasIds.includes(-1)
      ? null
      : this.sucursalesSeleccionadasIds;

  this.pmService
    .getCalendarioPm(
      this.anioSeleccionado,
      this.mesSeleccionado,
      sucursalesIds,
      this.semanaSeleccionada
    )
    .subscribe({
      next: (data) => {
        this.calendarioPmData = data;
        this.semanasDisponibles = data?.semanas || [];
        this.detalleSemanaSeleccionada = data?.detalle_semana_seleccionada || null;
        this.semanaSeleccionada = data?.detalle_semana_seleccionada?.semana_anio ?? this.semanaSeleccionada;

      },
      error: () => {
        this.calendarioPmData = null;
        this.semanasDisponibles = [];
        this.detalleSemanaSeleccionada = null;
      },
    });
}

obtenerClaseCargaCelda(totalProgramados: number): string {
  if (totalProgramados <= 0) {
    return 'pm-celda-vacia';
  }

  if (totalProgramados <= 2) {
    return 'pm-celda-baja';
  }

  if (totalProgramados <= 5) {
    return 'pm-celda-media';
  }

  return 'pm-celda-alta';
}



}