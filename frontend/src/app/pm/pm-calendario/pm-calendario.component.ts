// frontend/src/app/pm/pm-calendario/pm-calendario.component.ts


import { Component, OnInit, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { PmPreventivoService } from '../../services/pm-preventivo.service';
import { PmBitacoraDetalle, PmConfiguracionResumen, SucursalOption  } from '../../models/pm-preventivo.model';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatSelectModule } from '@angular/material/select';
import { SessionService } from '../../core/auth/session.service';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { MatInputModule } from '@angular/material/input';
import { MatButtonModule } from '@angular/material/button';



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
            MatInputModule,
            MatButtonModule,
            MatSnackBarModule,


  ],
  templateUrl: './pm-calendario.component.html',
  styleUrls: ['./pm-calendario.component.css'],
})
export class PmCalendarioComponent implements OnInit {

  private pmService = inject(PmPreventivoService);
  private session = inject(SessionService);
  private snack = inject(MatSnackBar);

  anioSeleccionado = new Date().getFullYear();
  mesSeleccionado = new Date().getMonth() + 1;
  semanaSeleccionada: number | null = null;

  semanasDisponibles: SemanaCalendarioPmOption[] = [];

  sucursalesCalendario: SucursalOption[] = [];
  sucursalesSeleccionadasIds: number[] = [];
  mostrarTodasLasSucursales = true;
  valorSeleccionSucursales: number[] = [-1];
  configuracionesPm: PmConfiguracionResumen[] = [];
  calendarioPmData: any = null;
  detalleSemanaSeleccionada: any = null;
  ocurrenciaSeleccionada: any = null;
  detalleBitacoraPmCalendario: PmBitacoraDetalle | null = null;
  mostrarRechazoPm = false;
  motivoRechazoPm = '';
  diasSemanaVista = this.crearDiasSemanaVacios();
  vistaActual: 'MES' | 'SEMANA' = 'MES';
  subcategoriaSeleccionada = 'TODAS';

readonly subcategoriasDisponibles = [
  { value: 'TODAS', label: 'Ver todo' },
  { value: 'spinning', label: 'Spinning' },
  { value: 'cardio', label: 'Cardio' },
  { value: 'selectorizado', label: 'Selectorizado' },
  { value: 'peso libre', label: 'Peso libre' },
];  



  ngOnInit(): void {
    this.cargarSucursalesCalendario();
    this.actualizarSemanasDisponibles();
    this.cargarCalendarioPm();
  }

  private obtenerSemanaActualDelMes(): number | null {
  const hoy = new Date();
  hoy.setHours(0, 0, 0, 0);

  const semanaActual = this.semanasDisponibles.find((semana) => {
    const fechaInicio = new Date(`${semana.fecha_inicio_iso}T00:00:00`);
    const fechaFin = new Date(`${semana.fecha_fin_iso}T23:59:59`);

    return hoy >= fechaInicio && hoy <= fechaFin;
  });

  return semanaActual?.semana_anio ?? this.semanasDisponibles[0]?.semana_anio ?? null;
}


actualizarSemanasDisponibles(): void {
  this.semanasDisponibles = generarSemanasDelMes(
    
    this.anioSeleccionado,
    this.mesSeleccionado
  );
  console.log('semanasDisponibles calendario PM:', this.semanasDisponibles);

  this.semanaSeleccionada = this.obtenerSemanaActualDelMes();
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
      this.semanaSeleccionada,
      this.subcategoriaSeleccionada
    )
    .subscribe({
      next: (data) => {
        console.log('detalleSemanaSeleccionada calendario PM', data?.detalle_semana_seleccionada);

console.log(
  'items semana calendario PM',
  (data?.detalle_semana_seleccionada?.items || []).map((item: any) => ({
    codigo: item.codigo_interno,
    fecha_programada: item.fecha_programada,
    estado_calendario: item.estado_calendario,
    tiene_bitacora: item.tiene_bitacora,
    bitacora_pm_id: item.bitacora_pm_id,
    validacion_estado: item.validacion_estado,
  }))
);


        this.calendarioPmData = data;
        this.semanasDisponibles = data?.semanas || [];
        this.detalleSemanaSeleccionada = data?.detalle_semana_seleccionada || null;
        this.semanaSeleccionada =
          data?.detalle_semana_seleccionada?.semana_anio ?? this.semanaSeleccionada;
        this.actualizarVistaSegunSemanaSeleccionada();

        this.construirVistaSemanalDetalle();
      },
      error: () => {
        this.calendarioPmData = null;
        this.semanasDisponibles = [];
        this.detalleSemanaSeleccionada = null;
        this.vistaActual = 'MES';
        this.diasSemanaVista = this.crearDiasSemanaVacios();
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

private obtenerDiaSemanaItem(item: any): number {
  if (typeof item?.dia_semana === 'number' && item.dia_semana >= 0 && item.dia_semana <= 6) {
    return item.dia_semana;
  }

  if (item?.fecha_programada) {
    const fecha = new Date(`${item.fecha_programada}T00:00:00`);
    if (!isNaN(fecha.getTime())) {
      return fecha.getDay();
    }
  }

  return -1;
}

private crearDiasSemanaVacios(): Array<{ key: number; label: string; fechaLabel: string; items: any[] }> {
  return [
    { key: 0, label: 'Domingo', fechaLabel: '', items: [] },
    { key: 1, label: 'Lunes', fechaLabel: '', items: [] },
    { key: 2, label: 'Martes', fechaLabel: '', items: [] },
    { key: 3, label: 'Miércoles', fechaLabel: '', items: [] },
    { key: 4, label: 'Jueves', fechaLabel: '', items: [] },
    { key: 5, label: 'Viernes', fechaLabel: '', items: [] },
    { key: 6, label: 'Sábado', fechaLabel: '', items: [] },
  ];
}

private construirVistaSemanalDetalle(): void {
  const baseDias = this.crearDiasSemanaVacios();
  const items = this.detalleSemanaSeleccionada?.items || [];
  const fechaInicioIso = this.detalleSemanaSeleccionada?.fecha_inicio_iso;

  if (fechaInicioIso) {
    const fechaInicio = new Date(`${fechaInicioIso}T00:00:00`);

    if (!isNaN(fechaInicio.getTime())) {
      for (let i = 0; i < baseDias.length; i++) {
        const fechaDia = new Date(fechaInicio);
        fechaDia.setDate(fechaInicio.getDate() + i);
        baseDias[i].fechaLabel = this.formatearFechaDiaSemana(fechaDia);
      }
    }
  }

  for (const item of items) {
    const diaSemana = this.obtenerDiaSemanaItem(item);

    if (diaSemana >= 0 && diaSemana <= 6) {
      baseDias[diaSemana].items.push(item);
    }
  }

  this.diasSemanaVista = baseDias;
}

seleccionarOcurrenciaSemana(item: any): void {
  this.ocurrenciaSeleccionada = item;

  this.mostrarRechazoPm = false;
  this.motivoRechazoPm = '';

  this.detalleBitacoraPmCalendario = null;

  if (item?.bitacora_pm_id) {
    this.pmService.getBitacoraDetalle(item.bitacora_pm_id).subscribe({
      next: (detalle) => {
        this.detalleBitacoraPmCalendario = detalle;
      },
      error: (err) => {
        const msg =
          err?.error?.detail ||
          err?.error?.message ||
          'No se pudo cargar el detalle de la bitácora PM';

        this.snack.open(msg, 'OK', { duration: 3000 });
      },
    });
  }
}
esOcurrenciaSeleccionada(item: any): boolean {
  return (
    this.ocurrenciaSeleccionada?.configuracion_pm_id === item?.configuracion_pm_id &&
    this.ocurrenciaSeleccionada?.fecha_programada === item?.fecha_programada
  );
}

obtenerClaseEstadoCalendario(item: any): string {
  const estado = (item?.estado_calendario || 'PROGRAMADO').toUpperCase();

  if (estado === 'PENDIENTE_VALIDACION') {
    return 'ocurrencia-pendiente-validacion';
  }

  if (estado === 'VALIDADO') {
    return 'ocurrencia-validada';
  }

  if (estado === 'RECHAZADO') {
    return 'ocurrencia-rechazada';
  }

  return 'ocurrencia-programada';
}

obtenerLabelEstadoCalendario(item: any): string {
  const estado = (item?.estado_calendario || 'PROGRAMADO').toUpperCase();

  if (estado === 'PENDIENTE_VALIDACION') {
    return 'Pendiente de validación';
  }

  if (estado === 'VALIDADO') {
    return 'Validado';
  }

  if (estado === 'RECHAZADO') {
    return 'Rechazado';
  }

  return 'Programado';
}

obtenerClaseBadgeEstadoCalendario(item: any): string {
  const estado = (item?.estado_calendario || 'PROGRAMADO').toUpperCase();

  if (estado === 'PENDIENTE_VALIDACION') {
    return 'badge-estado-pendiente';
  }

  if (estado === 'VALIDADO') {
    return 'badge-estado-validado';
  }

  if (estado === 'RECHAZADO') {
    return 'badge-estado-rechazado';
  }

  return 'badge-estado-programado';
}


obtenerClaseBadgeValidacionBitacora(): string {
  const estado = (this.detalleBitacoraPmCalendario?.validacion_estado || '').toUpperCase();

  if (estado === 'VALIDADO') {
    return 'badge-estado-validado';
  }

  if (estado === 'RECHAZADO') {
    return 'badge-estado-rechazado';
  }

  return 'badge-estado-pendiente';
}

obtenerLabelValidacionBitacora(): string {
  const estado = (this.detalleBitacoraPmCalendario?.validacion_estado || '').toUpperCase();

  if (estado === 'VALIDADO') {
    return 'Validado';
  }

  if (estado === 'RECHAZADO') {
    return 'Rechazado';
  }

  return 'Sin validación';
}


formatearResultadoBitacora(resultado: string | null | undefined): string {
  if (!resultado) return 'Sin resultado';

  const labels: Record<string, string> = {
    OK: 'Ok',
    FALLA: 'Falla',
    OBS: 'Observación',
  };

  return labels[resultado] || resultado;
}

tipoMantenimientoLabel(tipo: string | null | undefined): string {
  if (!tipo) return 'Sin tipo';

  const labels: Record<string, string> = {
    CORRECTIVO: 'Correctivo',
    PREVENTIVO: 'Preventivo',
    ESTETICO: 'Estético',
  };

  return labels[tipo] || tipo;
}


puedeValidarPm(): boolean {
  const user = this.session.getUser();
  const rol = (user?.rol || '').toString().trim().toUpperCase();

  return ['GERENTE', 'GERENTE_REGIONAL'].includes(rol);
}

puedeMostrarAccionesValidacionCalendario(): boolean {
  const bitacoraId = this.ocurrenciaSeleccionada?.bitacora_pm_id;
  const estado = (this.ocurrenciaSeleccionada?.estado_calendario || '').toUpperCase();

  return this.puedeValidarPm() && !!bitacoraId && estado === 'PENDIENTE_VALIDACION';
}

validarBitacoraPmDesdeCalendario(): void {
  const bitacoraId = this.ocurrenciaSeleccionada?.bitacora_pm_id;

  if (!bitacoraId) {
    this.snack.open('No hay bitácora seleccionada para validar', 'OK', {
      duration: 3000,
    });
    return;
  }

  this.pmService
    .crearValidacionPm({
      bitacora_pm_id: bitacoraId,
      decision: 'VALIDADO',
    })
    .subscribe({
      next: () => {
        this.snack.open('Bitácora validada correctamente', 'OK', {
          duration: 3000,
        });

        this.mostrarRechazoPm = false;
        this.motivoRechazoPm = '';
        this.cargarCalendarioPm();
      },
      error: (err) => {
        const msg =
          err?.error?.detail ||
          err?.error?.message ||
          'No se pudo validar la bitácora PM';

        this.snack.open(msg, 'OK', { duration: 3500 });
      },
    });
}

rechazarBitacoraPmDesdeCalendario(): void {
  const bitacoraId = this.ocurrenciaSeleccionada?.bitacora_pm_id;
  const motivo = this.motivoRechazoPm.trim();

  if (!bitacoraId) {
    this.snack.open('No hay bitácora seleccionada para rechazar', 'OK', {
      duration: 3000,
    });
    return;
  }

  if (!motivo) {
    this.snack.open('Debes capturar un motivo de rechazo', 'OK', {
      duration: 3000,
    });
    return;
  }

  this.pmService
    .crearValidacionPm({
      bitacora_pm_id: bitacoraId,
      decision: 'RECHAZADO',
      motivo,
    })
    .subscribe({
      next: () => {
        this.snack.open('Bitácora rechazada correctamente', 'OK', {
          duration: 3000,
        });

        this.mostrarRechazoPm = false;
        this.motivoRechazoPm = '';
        this.cargarCalendarioPm();
      },
      error: (err) => {
        const msg =
          err?.error?.detail ||
          err?.error?.message ||
          'No se pudo rechazar la bitácora PM';

        this.snack.open(msg, 'OK', { duration: 3500 });
      },
    });
}

textoBotonRechazoPmCalendario(): string {
  if (this.mostrarRechazoPm && this.motivoRechazoPm.trim()) {
    return 'Confirmar rechazo';
  }

  return 'Rechazar';
}

manejarBotonRechazoPmCalendario(): void {
  if (!this.mostrarRechazoPm) {
    this.mostrarRechazoPm = true;
    return;
  }

  if (!this.motivoRechazoPm.trim()) {
    this.snack.open('Debes capturar un motivo de rechazo', 'OK', {
      duration: 3000,
    });
    return;
  }

  this.rechazarBitacoraPmDesdeCalendario();
}


actualizarVistaSegunSemanaSeleccionada(): void {
  if (!this.semanaSeleccionada) {
    this.vistaActual = 'MES';
  }
}

irAVistaSemanal(): void {
  if (!this.semanaSeleccionada) {
    return;
  }

  this.vistaActual = 'SEMANA';
  this.construirVistaSemanalDetalle();
}


irAVistaMensual(): void {
  this.vistaActual = 'MES';
  this.ocurrenciaSeleccionada = null;
}

private formatearFechaDiaSemana(fecha: Date): string {
  const dia = String(fecha.getDate()).padStart(2, '0');
  const mes = String(fecha.getMonth() + 1).padStart(2, '0');
  return `${dia}/${mes}`;
}

manejarCambioSubcategoria(): void {
  this.cargarCalendarioPm();
}

puedeValidarOcurrenciaSeleccionada(): boolean {
  const item = this.ocurrenciaSeleccionada;

  return !!item
    && !!item.bitacora_pm_id
    && item.estado_calendario === 'PENDIENTE_VALIDACION';
}


}