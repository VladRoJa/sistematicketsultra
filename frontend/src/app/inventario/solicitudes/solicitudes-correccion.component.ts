import { Component, EventEmitter, Input, OnChanges, OnDestroy, Output, SimpleChanges } from '@angular/core';
import { CommonModule } from '@angular/common';
import { A11yModule } from '@angular/cdk/a11y';
import { FormsModule } from '@angular/forms';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { Subscription } from 'rxjs';

import {
  InventarioService,
  SolicitudCorreccionInput,
  SolicitudCorreccionInventario,
  TipoSolicitudInventario,
} from '../../services/inventario.service';

export interface ReferenciaSolicitud {
  inventario_id: number;
  sucursal_id: number;
  sucursal_nombre: string;
  nombre: string;
  codigo_interno: string | null;
  marca: string | null;
  tipo: string | null;
  unidad_medida: string | null;
  stock: number | null;
  categoria_inventario_id?: number | null;
  familia_equipo_id?: number | null;
}

export interface SucursalParaSolicitud {
  sucursal_id: number;
  sucursal: string;
}

type ModoSolicitud = 'crear' | 'seguimiento';
type VistaSolicitud = 'solicitud' | 'hallazgo' | 'seguimiento';

@Component({
  selector: 'app-solicitudes-correccion',
  standalone: true,
  imports: [CommonModule, FormsModule, MatIconModule, MatProgressSpinnerModule, A11yModule],
  templateUrl: './solicitudes-correccion.component.html',
  styleUrls: ['./solicitudes-correccion.component.css'],
})
export class SolicitudesCorreccionComponent implements OnChanges, OnDestroy {
  @Input() visible = false;
  @Input() referencia: ReferenciaSolicitud | null = null;
  @Input() vistaInicial: VistaSolicitud = 'seguimiento';
  @Input() sucursales: SucursalParaSolicitud[] = [];
  @Input() sucursalPreferida: number | 'global' = 'global';
  @Output() cerrar = new EventEmitter<void>();

  readonly tipos: { valor: TipoSolicitudInventario; etiqueta: string }[] = [
    { valor: 'QUANTITY_DIFFERENCE', etiqueta: 'Cantidad física distinta' },
    { valor: 'NOT_LOCATED', etiqueta: 'No localizado en sucursal' },
    { valor: 'MASTER_FIELD', etiqueta: 'Dato del artículo incorrecto' },
  ];
  readonly campos: { valor: keyof ReferenciaSolicitud; etiqueta: string; numerico?: boolean }[] = [
    { valor: 'nombre', etiqueta: 'Nombre' },
    { valor: 'marca', etiqueta: 'Marca' },
    { valor: 'codigo_interno', etiqueta: 'Código interno' },
    { valor: 'tipo', etiqueta: 'Tipo' },
    { valor: 'unidad_medida', etiqueta: 'Unidad de medida' },
    { valor: 'categoria_inventario_id', etiqueta: 'ID categoría oficial', numerico: true },
    { valor: 'familia_equipo_id', etiqueta: 'ID familia oficial', numerico: true },
  ];
  readonly etiquetasTipo: Record<TipoSolicitudInventario, string> = {
    QUANTITY_DIFFERENCE: 'Cantidad física distinta',
    NOT_LOCATED: 'Artículo no localizado',
    MASTER_FIELD: 'Dato incorrecto',
    UNREGISTERED_FIND: 'Artículo no registrado',
  };

  modo: ModoSolicitud = 'crear';
  tipo: TipoSolicitudInventario = 'QUANTITY_DIFFERENCE';
  campo: keyof ReferenciaSolicitud = 'nombre';
  sucursalId: number | null = null;
  cantidadFisica: number | null = null;
  nuevoTexto = '';
  nuevoId: number | null = null;
  motivo = '';
  evidencia = '';
  fechaObservacion = '';
  hallazgoNombre = '';
  hallazgoMarca = '';
  hallazgoTipo = '';
  hallazgoCodigo = '';

  guardando = false;
  guardado: SolicitudCorreccionInventario | null = null;
  advertenciaDuplicado = false;
  errorGuardar = '';
  private idempotencyKey: string | null = null;
  private peticionGuardar?: Subscription;

  cargandoListado = false;
  errorListado = '';
  solicitudes: SolicitudCorreccionInventario[] = [];
  totalSolicitudes = 0;
  pagina = 1;
  readonly tamanoPagina = 10;
  filtroSucursal: number | 'todas' = 'todas';
  filtroEstado: 'PENDING' | 'APPROVED' | 'REJECTED' | 'todos' = 'todos';
  filtroTipo: TipoSolicitudInventario | 'todos' = 'todos';
  detalle: SolicitudCorreccionInventario | null = null;
  detalleIdAbierto: number | null = null;
  errorDetalle = '';
  seleccionados = new Set<number>();
  private peticionListado?: Subscription;
  private peticionDetalle?: Subscription;
  private disparadorDetalle: HTMLElement | null = null;
  private consultaVersion = 0;

  constructor(private readonly inventario: InventarioService) {}

  ngOnChanges(changes: SimpleChanges): void {
    if (changes['visible'] && this.visible) {
      this.iniciar();
    }
  }

  ngOnDestroy(): void {
    this.cancelarPeticiones();
  }

  private cancelarPeticiones(): void {
    ++this.consultaVersion;
    this.peticionGuardar?.unsubscribe();
    this.peticionListado?.unsubscribe();
    this.peticionDetalle?.unsubscribe();
  }

  private iniciar(): void {
    this.cancelarPeticiones();
    this.tipo = this.vistaInicial === 'hallazgo' ? 'UNREGISTERED_FIND' : 'QUANTITY_DIFFERENCE';
    this.modo = this.vistaInicial === 'seguimiento' ? 'seguimiento' : 'crear';
    this.campo = 'nombre';
    this.sucursalId = this.referencia?.sucursal_id ??
      (typeof this.sucursalPreferida === 'number' ? this.sucursalPreferida :
        this.sucursales.length === 1 ? this.sucursales[0].sucursal_id : null);
    this.cantidadFisica = null;
    this.nuevoTexto = '';
    this.nuevoId = null;
    this.motivo = '';
    this.evidencia = '';
    this.fechaObservacion = '';
    this.hallazgoNombre = '';
    this.hallazgoMarca = '';
    this.hallazgoTipo = '';
    this.hallazgoCodigo = '';
    this.guardando = false;
    this.guardado = null;
    this.advertenciaDuplicado = false;
    this.errorGuardar = '';
    this.idempotencyKey = null;
    this.errorListado = '';
    this.solicitudes = [];
    this.totalSolicitudes = 0;
    this.pagina = 1;
    this.filtroSucursal = this.sucursalId ?? 'todas';
    this.filtroEstado = 'todos';
    this.filtroTipo = 'todos';
    this.detalle = null;
    this.detalleIdAbierto = null;
    this.errorDetalle = '';
    this.seleccionados = new Set<number>();
    if (this.modo === 'seguimiento') this.cargarSolicitudes();
  }

  cerrarPanel(): void {
    if (this.guardando) return;
    this.cancelarPeticiones();
    this.cerrar.emit();
  }

  abrirSeguimiento(): void {
    if (this.guardando) return;
    this.modo = 'seguimiento';
    this.detalle = null;
    this.detalleIdAbierto = null;
    this.seleccionados = new Set<number>();
    this.pagina = 1;
    this.cargarSolicitudes();
  }

  volverFormulario(): void {
    this.modo = 'crear';
    this.detalle = null;
  }

  seleccionarTipo(valor: TipoSolicitudInventario): void {
    if (!this.referencia && valor !== 'UNREGISTERED_FIND') return;
    this.tipo = valor;
    this.campo = 'nombre';
    this.nuevoTexto = '';
    this.nuevoId = null;
    this.cantidadFisica = null;
    this.modificado();
  }

  modificado(): void {
    this.idempotencyKey = null;
    this.errorGuardar = '';
    this.guardado = null;
    this.advertenciaDuplicado = false;
  }

  get esHallazgo(): boolean {
    return this.tipo === 'UNREGISTERED_FIND';
  }

  get requiereEvidenciaFisica(): boolean {
    return this.tipo === 'NOT_LOCATED' || this.tipo === 'UNREGISTERED_FIND';
  }

  get campoNumerico(): boolean {
    return !!this.campos.find(c => c.valor === this.campo)?.numerico;
  }

  get maxLongitudCampo(): number {
    return this.campo === 'tipo' ? 20 :
      this.campo === 'codigo_interno' || this.campo === 'unidad_medida' ? 50 :
      this.campo === 'marca' ? 100 : 255;
  }

  cerrarDetalle(restaurarFoco = true): void {
    this.peticionDetalle?.unsubscribe();
    this.detalle = null;
    this.detalleIdAbierto = null;
    this.errorDetalle = '';
    // Regresar al botón Detalles; no perder el contexto ni la selección.
    const disparador = this.disparadorDetalle;
    this.disparadorDetalle = null;
    // Esperar a que Angular retire inert y el trap del dialogo al cerrar.
    if (restaurarFoco && disparador) {
      queueMicrotask(() => {
        if (disparador.isConnected) disparador.focus();
      });
    }
  }

  // Solo se pueden seleccionar solicitudes pendientes de la página actual.
  // La selección se reinicia en cada búsqueda o cambio de página: no alcanza
  // silenciosamente otras sucursales, filtros o páginas.
  get pendientesPagina(): SolicitudCorreccionInventario[] {
    return this.solicitudes.filter(solicitud => solicitud.estado === 'PENDING');
  }

  get totalSeleccionados(): number {
    return this.seleccionados.size;
  }

  get todosSeleccionadosPagina(): boolean {
    return this.pendientesPagina.length > 0 &&
      this.pendientesPagina.every(solicitud => this.seleccionados.has(solicitud.id));
  }

  get algunosSeleccionadosPagina(): boolean {
    return this.pendientesPagina.some(solicitud => this.seleccionados.has(solicitud.id)) &&
      !this.todosSeleccionadosPagina;
  }

  estaSeleccionada(id: number): boolean {
    return this.seleccionados.has(id);
  }

  alternarSeleccion(id: number): void {
    const solicitud = this.pendientesPagina.find(item => item.id === id);
    if (!solicitud) return;
    const nuevaSeleccion = new Set(this.seleccionados);
    if (nuevaSeleccion.has(id)) nuevaSeleccion.delete(id);
    else nuevaSeleccion.add(id);
    this.seleccionados = nuevaSeleccion;
  }

  alternarPagina(): void {
    const nuevaSeleccion = new Set<number>();
    if (!this.todosSeleccionadosPagina) {
      for (const solicitud of this.pendientesPagina) nuevaSeleccion.add(solicitud.id);
    }
    this.seleccionados = nuevaSeleccion;
  }

  resumenSolicitud(solicitud: SolicitudCorreccionInventario): string {
    if (solicitud.tipo === 'UNREGISTERED_FIND') {
      return solicitud.hallazgo_provisional?.['nombre'] || 'Artículo sin referencia oficial';
    }
    if (solicitud.tipo === 'MASTER_FIELD') {
      return `${solicitud.campo || 'Dato maestro'}: ${this.mostrarDato(solicitud.valor_original)} → ${this.mostrarDato(solicitud.valor_propuesto)}`;
    }
    if (solicitud.tipo === 'QUANTITY_DIFFERENCE') {
      const original = solicitud.valor_original as { stock?: number } | null;
      const propuesto = solicitud.valor_propuesto as { cantidad_fisica?: number } | null;
      return `Existencia: ${this.mostrarDato(original?.stock)} → ${this.mostrarDato(propuesto?.cantidad_fisica)}`;
    }
    return 'No localizado físicamente';
  }


  get valorOficial(): string | number | null {
    if (!this.referencia) return null;
    const value = this.referencia[this.campo];
    return typeof value === 'string' || typeof value === 'number' ? value : null;
  }

  get puedeEnviar(): boolean {
    if (this.guardando || this.guardado || !this.sucursalId || this.motivo.trim().length < 10 ||
        this.motivo.trim().length > 2000 || this.evidencia.length > 2000) return false;
    if (this.requiereEvidenciaFisica && (
        !this.fechaObservacion ||
        this.evidencia.trim().length < 20 ||
        this.evidencia.trim().length > 2000
    )) return false;
    if (this.esHallazgo) return !!this.hallazgoNombre.trim() && this.hallazgoNombre.length <= 255 &&
      (!this.hallazgoTipo || this.hallazgoTipo.length <= 40) &&
      (!this.hallazgoMarca || this.hallazgoMarca.length <= 100) &&
      (!this.hallazgoCodigo || this.hallazgoCodigo.length <= 50);
    if (!this.referencia || this.referencia.stock === null) return false;
    if (this.tipo === 'QUANTITY_DIFFERENCE') {
      return this.cantidadFisica !== null && Number.isInteger(this.cantidadFisica) &&
        this.cantidadFisica > 0 && this.cantidadFisica !== this.referencia.stock;
    }
    if (this.tipo === 'NOT_LOCATED') return this.referencia.stock > 0;
    if (this.tipo === 'MASTER_FIELD') {
      if (this.campoNumerico) return this.nuevoId !== null && Number.isInteger(this.nuevoId) &&
        this.nuevoId > 0 && this.nuevoId !== this.valorOficial;
      return !!this.nuevoTexto.trim() && this.nuevoTexto.trim() !== this.valorOficial &&
        this.nuevoTexto.length <= this.maxLongitudCampo;
    }
    return false;
  }

  private crearPayload(): SolicitudCorreccionInput | null {
    if (!this.puedeEnviar || this.sucursalId === null) return null;
    this.idempotencyKey ||= crypto.randomUUID();
    const payload: SolicitudCorreccionInput = {
      tipo: this.tipo,
      sucursal_id: this.sucursalId,
      motivo: this.motivo.trim(),
      idempotency_key: this.idempotencyKey,
    };
    if (this.fechaObservacion) payload.fecha_observacion_local = this.fechaObservacion;
    if (this.evidencia.trim()) payload.evidencia_descriptiva = this.evidencia.trim();

    if (this.esHallazgo) {
      payload.hallazgo_provisional = { nombre: this.hallazgoNombre.trim() };
      if (this.hallazgoTipo.trim()) payload.hallazgo_provisional.tipo = this.hallazgoTipo.trim();
      if (this.hallazgoMarca.trim()) payload.hallazgo_provisional.marca = this.hallazgoMarca.trim();
      if (this.hallazgoCodigo.trim()) payload.hallazgo_provisional.codigo_interno = this.hallazgoCodigo.trim();
    } else if (this.referencia) {
      payload.inventario_id = this.referencia.inventario_id;
      if (this.tipo === 'MASTER_FIELD') {
        payload.campo = this.campo;
        payload.valor_original = this.valorOficial;
        payload.valor_propuesto = this.campoNumerico ? this.nuevoId : this.nuevoTexto.trim();
      } else {
        payload.valor_original = { stock: this.referencia.stock };
        payload.valor_propuesto = this.tipo === 'NOT_LOCATED'
          ? { no_localizado: true } : { cantidad_fisica: this.cantidadFisica };
      }
    }
    return payload;
  }

  enviar(): void {
    const payload = this.crearPayload();
    if (!payload) return;
    this.guardando = true;
    this.errorGuardar = '';
    this.peticionGuardar?.unsubscribe();
    this.peticionGuardar = this.inventario.crearSolicitudCorreccion(payload).subscribe({
      next: ({ solicitud, possible_pending_duplicate }) => {
        this.guardando = false;
        this.guardado = solicitud;
        this.advertenciaDuplicado = !!possible_pending_duplicate;
      },
      error: (err: { status?: number }) => {
        this.guardando = false;
        this.errorGuardar = err?.status === 409
          ? 'Los datos oficiales cambiaron o la solicitud ya existe con otro contenido. Actualiza Existencias y vuelve a revisar.'
          : err?.status === 403
          ? 'Tu perfil no tiene permiso para registrar una solicitud en esta sucursal.'
          : 'No se pudo guardar. Puedes reintentar sin generar otra solicitud.';
      },
    });
  }

  get totalPaginas(): number {
    return Math.max(1, Math.ceil(this.totalSolicitudes / this.tamanoPagina));
  }

  cambiarPagina(delta: number): void {
    const siguiente = this.pagina + delta;
    if (siguiente < 1 || siguiente > this.totalPaginas) return;
    this.pagina = siguiente;
    this.cargarSolicitudes();
  }

  cambiarFiltros(): void {
    this.pagina = 1;
    this.cargarSolicitudes();
  }

  cargarSolicitudes(): void {
    this.peticionListado?.unsubscribe();
    this.cerrarDetalle(false);
    this.seleccionados = new Set<number>();
    const version = ++this.consultaVersion;
    this.cargandoListado = true;
    this.errorListado = '';
    this.solicitudes = [];
    const params: {
      page: number; per_page: number; sucursal_id?: number;
      tipo?: TipoSolicitudInventario; estado?: 'PENDING' | 'APPROVED' | 'REJECTED';
    } = { page: this.pagina, per_page: this.tamanoPagina };
    if (this.filtroSucursal !== 'todas') params.sucursal_id = Number(this.filtroSucursal);
    if (this.filtroEstado !== 'todos') params.estado = this.filtroEstado;
    if (this.filtroTipo !== 'todos') params.tipo = this.filtroTipo;
    this.peticionListado = this.inventario.listarSolicitudesCorreccion(params).subscribe({
      next: (resultado) => {
        if (version !== this.consultaVersion) return;
        this.solicitudes = resultado.items;
        this.totalSolicitudes = resultado.total;
        this.cargandoListado = false;
      },
      error: () => {
        if (version !== this.consultaVersion) return;
        this.cargandoListado = false;
        this.errorListado = 'No fue posible consultar las solicitudes de tu alcance.';
      },
    });
  }

  toggleDetalle(id: number, evento?: Event): void {
    if (this.detalleIdAbierto === id) {
      this.cerrarDetalle();
      return;
    }
    // La referencia al botón solo se usa para restaurar el foco al cerrar.
    this.disparadorDetalle = (evento?.currentTarget as HTMLElement | null) ?? null;
    this.consultarDetalle(id);
  }

  reintentarDetalle(): void {
    if (this.detalleIdAbierto !== null) this.consultarDetalle(this.detalleIdAbierto);
  }

  consultarDetalle(id: number): void {
    this.peticionDetalle?.unsubscribe();
    this.detalle = null;
    this.errorDetalle = '';
    this.detalleIdAbierto = id;
    this.peticionDetalle = this.inventario.obtenerSolicitudCorreccion(id).subscribe({
      next: ({ solicitud }) => {
        if (this.detalleIdAbierto === id) this.detalle = solicitud;
      },
      error: () => {
        if (this.detalleIdAbierto === id) {
          this.errorDetalle = 'No fue posible abrir este detalle.';
        }
      },
    });
  }

  mostrarDato(value: unknown): string {
    if (value === null || value === undefined) return 'Sin dato';
    if (typeof value === 'object') return JSON.stringify(value);
    return String(value);
  }

  nombreSucursal(id: number): string {
    return this.sucursales.find(s => s.sucursal_id === id)?.sucursal || 'Sucursal ' + id;
  }
}
