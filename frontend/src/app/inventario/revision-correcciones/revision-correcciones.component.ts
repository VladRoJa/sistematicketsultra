import { CommonModule } from '@angular/common';
import { Component, OnDestroy, OnInit } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { A11yModule } from '@angular/cdk/a11y';
import { MatIconModule } from '@angular/material/icon';
import { Subscription } from 'rxjs';

import {
  InventarioService, LoteDecisionesInventario, ResolucionHallazgo,
  ResolucionNoLocalizado, RevisionCorreccionesContexto,
  SolicitudCorreccionInventario, TipoSolicitudInventario,
} from '../../services/inventario.service';

type Decision = 'APPROVED' | 'REJECTED';
type EdicionResolucion = {
  accion: 'AJUSTAR_A_CERO' | 'VINCULAR_EXISTENTE';
  inventario_id: number | null;
  stock_esperado: number | null;
  cantidad_fisica: number | null;
  justificacion: string;
};

@Component({
  selector: 'app-revision-correcciones',
  standalone: true,
  imports: [CommonModule, FormsModule, A11yModule, MatIconModule],
  templateUrl: './revision-correcciones.component.html',
  styleUrls: ['./revision-correcciones.component.css'],
})
export class RevisionCorreccionesComponent implements OnInit, OnDestroy {
  readonly tipos: Record<TipoSolicitudInventario, string> = {
    MASTER_FIELD: 'Dato maestro',
    QUANTITY_DIFFERENCE: 'Diferencia de cantidad',
    NOT_LOCATED: 'No localizado',
    UNREGISTERED_FIND: 'Hallazgo sin registro',
  };
  contexto: RevisionCorreccionesContexto | null = null;
  iniciando = true;
  cargando = false;
  procesando = false;
  error = '';
  aviso = '';
  solicitudes: SolicitudCorreccionInventario[] = [];
  total = 0;
  pagina = 1;
  readonly porPagina = 10;
  filtroSucursal: number | 'todas' = 'todas';
  filtroEstado: 'PENDING' | 'APPROVED' | 'REJECTED' = 'PENDING';
  filtroTipo: TipoSolicitudInventario | 'todos' = 'todos';
  seleccion = new Set<number>();
  decision: Decision | null = null;
  motivo = '';
  confirmo = false;
  resoluciones: Record<number, EdicionResolucion> = {};
  errorDecision = '';
  private key: string | null = null;
  private fingerprint = '';
  private subContexto?: Subscription;
  private subListado?: Subscription;
  private subDecision?: Subscription;
  private consulta = 0;

  constructor(private readonly inventario: InventarioService) {}

  ngOnInit(): void {
    this.subContexto = this.inventario.contextoRevisionCorrecciones().subscribe({
      next: contexto => {
        this.contexto = contexto;
        this.iniciando = false;
        this.cargar();
      },
      error: () => {
        this.iniciando = false;
        this.error = 'No tienes permiso de revisión E3 o no se pudo verificar tu sesión.';
      },
    });
  }

  ngOnDestroy(): void {
    this.subContexto?.unsubscribe();
    this.subListado?.unsubscribe();
    this.subDecision?.unsubscribe();
    ++this.consulta;
  }

  get seleccionadas(): SolicitudCorreccionInventario[] {
    return this.solicitudes.filter(s => this.seleccion.has(s.id) && s.estado === 'PENDING');
  }

  get paginas(): number {
    return Math.max(1, Math.ceil(this.total / this.porPagina));
  }

  get puedePreparar(): boolean {
    return !this.cargando && !this.procesando && this.seleccionadas.length > 0;
  }

  get aprobacionEspecialIndividual(): boolean {
    if (this.decision !== 'APPROVED' || this.seleccionadas.length !== 1) return false;
    const tipo = this.seleccionadas[0].tipo;
    return tipo === 'NOT_LOCATED' || tipo === 'UNREGISTERED_FIND';
  }

  faltaEvidenciaFisica(s: SolicitudCorreccionInventario): boolean {
    if (s.tipo !== 'NOT_LOCATED' && s.tipo !== 'UNREGISTERED_FIND') return false;
    const evidencia = String(s.evidencia_descriptiva || '').trim();
    return !s.fecha_observacion_local || evidencia.length < 20 || evidencia.length > 2000;
  }

  faltaCodigoHallazgo(s: SolicitudCorreccionInventario): boolean {
    return s.tipo === 'UNREGISTERED_FIND' &&
      !String(s.hallazgo_provisional?.['codigo_interno'] || '').trim();
  }

  cantidadCeroRequiereNoLocalizado(s: SolicitudCorreccionInventario): boolean {
    if (s.tipo !== 'QUANTITY_DIFFERENCE') return false;
    const proposal = s.valor_propuesto as { cantidad_fisica?: unknown } | null;
    return proposal?.cantidad_fisica === 0;
  }

  get puedeConfirmar(): boolean {
    const longitudMinima = this.aprobacionEspecialIndividual ? 20 : 10;
    if (!this.decision || this.procesando || !this.confirmo ||
        this.motivo.trim().length < longitudMinima || this.motivo.trim().length > 2000 ||
        !this.seleccionadas.length) return false;
    if (this.decision === 'REJECTED') return true;
    return this.seleccionadas.every(s => {
      if (s.tipo === 'MASTER_FIELD' && !this.contexto?.corporativo) return false;
      if (this.cantidadCeroRequiereNoLocalizado(s)) return false;
      if (s.tipo === 'QUANTITY_DIFFERENCE' || s.tipo === 'MASTER_FIELD') return true;
      if (this.faltaEvidenciaFisica(s) || this.faltaCodigoHallazgo(s)) return false;
      const r = this.resoluciones[s.id];
      if (!r) return false;
      const fundamento = this.aprobacionEspecialIndividual
        ? this.motivo.trim() : r.justificacion.trim();
      if (fundamento.length < 20 || fundamento.length > 2000) return false;
      if (s.tipo === 'NOT_LOCATED') {
        return r.accion === 'AJUSTAR_A_CERO' &&
          Number.isInteger(r.stock_esperado) && (r.stock_esperado ?? 0) > 0;
      }
      if (s.tipo === 'UNREGISTERED_FIND') {
        return r.accion === 'VINCULAR_EXISTENTE' &&
          Number.isInteger(r.inventario_id) && (r.inventario_id ?? 0) > 0 &&
          Number.isInteger(r.stock_esperado) && (r.stock_esperado ?? -1) >= 0 &&
          Number.isInteger(r.cantidad_fisica) &&
          (r.cantidad_fisica ?? 0) > (r.stock_esperado ?? 0);
      }
      return false;
    });
  }

  cargar(): void {
    if (!this.contexto || this.procesando) return;
    this.subListado?.unsubscribe();
    this.cerrarDecision();
    this.seleccion = new Set<number>();
    const version = ++this.consulta;
    this.cargando = true;
    this.error = '';
    this.solicitudes = [];
    const params: {
      page: number; per_page: number; sucursal_id?: number;
      estado: 'PENDING' | 'APPROVED' | 'REJECTED'; tipo?: TipoSolicitudInventario;
    } = { page: this.pagina, per_page: this.porPagina, estado: this.filtroEstado };
    if (this.filtroSucursal !== 'todas') params.sucursal_id = this.filtroSucursal;
    if (this.filtroTipo !== 'todos') params.tipo = this.filtroTipo;
    this.subListado = this.inventario.listarRevisionCorrecciones(params).subscribe({
      next: data => {
        if (version !== this.consulta) return;
        this.solicitudes = data.items;
        this.total = data.total;
        this.cargando = false;
      },
      error: () => {
        if (version !== this.consulta) return;
        this.error = 'No se pudo consultar la bandeja autorizada. Revisa los permisos o reintenta.';
        this.cargando = false;
      },
    });
  }

  cambiarFiltros(): void {
    this.pagina = 1;
    this.cargar();
  }

  cambiarPagina(delta: number): void {
    if (this.pagina + delta < 1 || this.pagina + delta > this.paginas) return;
    this.pagina += delta;
    this.cargar();
  }

  marcar(id: number): void {
    const row = this.solicitudes.find(s => s.id === id && s.estado === 'PENDING');
    if (!row || this.procesando) return;
    const next = new Set(this.seleccion);
    if (next.has(id)) next.delete(id);
    else if (next.size < 10) next.add(id);
    this.seleccion = next;
  }

  marcarPagina(): void {
    if (this.procesando) return;
    const pending = this.solicitudes.filter(s => s.estado === 'PENDING');
    this.seleccion = pending.every(s => this.seleccion.has(s.id))
      ? new Set<number>() : new Set(pending.slice(0, 10).map(s => s.id));
  }

  preparar(decision: Decision): void {
    if (!this.puedePreparar) return;
    this.decision = decision;
    this.motivo = '';
    this.confirmo = false;
    this.errorDecision = '';
    this.key = null;
    this.fingerprint = '';
    this.resoluciones = {};
    if (decision === 'APPROVED') {
      for (const s of this.seleccionadas) {
        if (s.tipo === 'NOT_LOCATED') {
          const esperado = s.baseline_canonico['stock'];
          this.resoluciones[s.id] = {
            accion: 'AJUSTAR_A_CERO', inventario_id: null,
            stock_esperado: typeof esperado === 'number' ? esperado : null,
            cantidad_fisica: null, justificacion: '',
          };
        } else if (s.tipo === 'UNREGISTERED_FIND') {
          this.resoluciones[s.id] = {
            accion: 'VINCULAR_EXISTENTE', inventario_id: null,
            stock_esperado: null, cantidad_fisica: null, justificacion: '',
          };
        }
      }
    }
  }

  cerrarDecision(): void {
    if (this.procesando) return;
    this.decision = null;
    this.errorDecision = '';
    this.confirmo = false;
  }

  actualizado(): void {
    this.errorDecision = '';
    this.key = null;
    this.fingerprint = '';
    this.confirmo = false;
  }

  ejecutar(): void {
    if (!this.puedeConfirmar || !this.decision) return;
    const payload: LoteDecisionesInventario = {
      decision: this.decision,
      solicitud_ids: this.seleccionadas.map(s => s.id).sort((a, b) => a - b),
      motivo: this.motivo.trim(), idempotency_key: '',
    };
    if (this.decision === 'APPROVED') {
      const resoluciones: LoteDecisionesInventario['resoluciones'] = {};
      for (const s of this.seleccionadas) {
        const r = this.resoluciones[s.id];
        if (s.tipo === 'NOT_LOCATED' && r) {
          resoluciones[String(s.id)] = {
            accion: 'AJUSTAR_A_CERO', stock_esperado: r.stock_esperado!,
            justificacion: this.aprobacionEspecialIndividual
              ? this.motivo.trim() : r.justificacion.trim(),
          } as ResolucionNoLocalizado;
        } else if (s.tipo === 'UNREGISTERED_FIND' && r) {
          resoluciones[String(s.id)] = {
            accion: 'VINCULAR_EXISTENTE', inventario_id: r.inventario_id!,
            stock_esperado: r.stock_esperado!, cantidad_fisica: r.cantidad_fisica!,
            justificacion: this.aprobacionEspecialIndividual
              ? this.motivo.trim() : r.justificacion.trim(),
          } as ResolucionHallazgo;
        }
      }
      if (Object.keys(resoluciones).length) payload.resoluciones = resoluciones;
    }
    const fingerprint = JSON.stringify(payload);
    if (!this.key || this.fingerprint !== fingerprint) {
      this.key = crypto.randomUUID();
      this.fingerprint = fingerprint;
    }
    payload.idempotency_key = this.key;
    this.procesando = true;
    this.errorDecision = '';
    this.subDecision?.unsubscribe();
    this.subDecision = this.inventario.decidirCorreccionesLote(payload).subscribe({
      next: resultado => {
        this.procesando = false;
        this.decision = null;
        this.aviso = `Lote #${resultado.lote_id}: ${resultado.items.length} solicitudes ${payload.decision === 'APPROVED' ? 'autorizadas' : 'rechazadas'}.`;
        this.cargar();
      },
      error: (err: { status?: number; error?: { detail?: string } }) => {
        this.procesando = false;
        this.errorDecision = err.error?.detail ||
          (err.status === 403 ? 'Se revocó el permiso de una solicitud. Actualiza la bandeja.' :
          err.status === 409 ? 'Una solicitud cambió. Revisa los valores antes de reintentar.' :
          'No fue posible confirmar el lote. Reintenta sin cambiar su contenido.');
      },
    });
  }

  textoValor(valor: unknown): string {
    if (valor == null) return 'Sin dato';
    return typeof valor === 'object' ? JSON.stringify(valor) : String(valor);
  }

  sucursalNombre(id: number): string {
    return this.contexto?.sucursales.find(s => s.sucursal_id === id)?.sucursal || `Sucursal #${id}`;
  }

  nombreReferencia(s: SolicitudCorreccionInventario): string {
    if (s.tipo === 'UNREGISTERED_FIND') {
      return s.hallazgo_provisional?.['nombre'] || 'Hallazgo sin nombre';
    }
    return s.referencia_oficial?.nombre || 'Nombre no disponible';
  }

  codigoReferencia(s: SolicitudCorreccionInventario): string {
    if (s.tipo === 'UNREGISTERED_FIND') {
      return s.hallazgo_provisional?.['codigo_interno'] || 'Sin código físico';
    }
    return s.referencia_oficial?.codigo_interno || 'Sin código interno';
  }

  cambioPropuesto(s: SolicitudCorreccionInventario): string {
    if (s.tipo === 'NOT_LOCATED') {
      const anterior = s.valor_original as { stock?: number } | null;
      const stock = anterior?.stock ?? s.baseline_canonico?.['stock'];
      return `Stock oficial: ${this.textoValor(stock)} → 0 · Ajuste solicitado`;
    }
    if (s.tipo === 'QUANTITY_DIFFERENCE') {
      const anterior = s.valor_original as { stock?: number } | null;
      const propuesta = s.valor_propuesto as { cantidad_fisica?: number } | null;
      return `Stock oficial: ${this.textoValor(anterior?.stock ?? s.baseline_canonico?.['stock'])} → ${this.textoValor(propuesta?.cantidad_fisica)} · Conteo físico`;
    }
    if (s.tipo === 'MASTER_FIELD') {
      return `${s.campo || 'Dato maestro'}: ${this.textoValor(s.valor_original)} → ${this.textoValor(s.valor_propuesto)}`;
    }
    const hallazgo = s.hallazgo_provisional;
    return `Hallazgo: ${hallazgo?.['nombre'] || 'Sin nombre'} · Código físico: ${hallazgo?.['codigo_interno'] || 'Sin código'}`;
  }

  resumen(s: SolicitudCorreccionInventario): string {
    return s.tipo === 'UNREGISTERED_FIND'
      ? s.hallazgo_provisional?.['nombre'] || 'Hallazgo provisional'
      : s.tipo === 'MASTER_FIELD'
      ? `${s.campo}: ${this.textoValor(s.valor_original)} → ${this.textoValor(s.valor_propuesto)}`
      : s.tipo === 'QUANTITY_DIFFERENCE'
      ? `Conteo: ${this.textoValor(s.valor_original)} → ${this.textoValor(s.valor_propuesto)}`
      : 'Equipo reportado como no localizado';
  }
}
