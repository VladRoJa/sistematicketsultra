import { Component, OnDestroy, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatTableModule } from '@angular/material/table';
import { Subscription } from 'rxjs';

import { SessionService } from '../../core/auth/session.service';
import { InventarioService } from '../../services/inventario.service';

interface SucursalInventario {
  sucursal_id: number;
  sucursal: string;
}

interface ExistenciaInventario {
  inventario_id: number;
  sucursal_id: number;
  sucursal_nombre: string;
  nombre: string;
  codigo_interno: string | null;
  tipo: string | null;
  marca: string | null;
  proveedor: string | null;
  categoria: string | null;
  subcategoria?: string | null;
  categoria_inventario_id?: number | null;
  categoria_catalogo?: string | null;
  familia_equipo_id?: number | null;
  familia_equipo?: { id: number; key: string; nombre: string } | null;
  unidad_medida: string | null;
  stock: number | null;
}

interface CategoriaExistencia {
  nombre: string;
  cantidad: number;
  porcentaje: number;
  color: string;
}

interface FamiliaExistencia {
  nombre: string;
  cantidad: number;
  sinClasificar: boolean;
}

const ROLES_CON_ALCANCE_GLOBAL = new Set([
  'ADMIN',
  'ADMINISTRADOR',
  'SUPER_ADMIN',
  'MANTENIMIENTO',
  'SISTEMAS',
  'TECNICO',
]);

// Gate de presentación E1: GERENTE y GERENTE_REGIONAL no participan
// en el piloto. El backend sigue siendo la autoridad de permisos.
const ROLES_PILOTO_V2 = new Set([
  ...ROLES_CON_ALCANCE_GLOBAL,
  'SR_MANTENIMIENTO',
  'AUX_MANTENIMIENTO',
]);

@Component({
  selector: 'app-existencias',
  standalone: true,
  imports: [
    CommonModule,
    FormsModule,
    MatIconModule,
    MatProgressSpinnerModule,
    MatTableModule,
  ],
  templateUrl: './existencias.component.html',
  styleUrls: ['./existencias.component.css'],
})
export class ExistenciasComponent implements OnInit, OnDestroy {
  readonly displayedColumns = [
    'id', 'nombre', 'codigo_interno', 'tipo', 'marca',
    'proveedor', 'categoria', 'familia', 'unidad', 'stock', 'sucursal',
  ];
  readonly pageSize = 40;

  puedeVerGlobal = false;
  puedeConsultarVista = false;
  sucursales: SucursalInventario[] = [];
  sucursalSeleccionada: number | 'global' = 'global';

  existencias: ExistenciaInventario[] = [];
  existenciasFiltradas: ExistenciaInventario[] = [];
  filasPagina: ExistenciaInventario[] = [];
  categorias: string[] = [];
  categoriasDisponibles: string[] = [];
  composicion: CategoriaExistencia[] = [];
  familias: string[] = [];
  familiasDisponibles: string[] = [];
  mostrarFiltroFamilia = false;
  composicionFamilias: FamiliaExistencia[] = [];
  totalEquiposGimnasio = 0;
  equiposSinFamilia = 0;

  totalReferencias = 0;
  referenciasConStock = 0;
  referenciasSinStock = 0;
  totalCategorias = 0;

  busqueda = '';
  categoriaSeleccionada = 'todas';
  familiaSeleccionada = 'todas';
  estadoStock = 'todos';
  paginaActual = 0;
  loading = false;
  error = '';

  private peticionExistencias?: Subscription;
  private peticionSucursales?: Subscription;
  private versionConsulta = 0;

  constructor(
    private readonly inventarioService: InventarioService,
    private readonly session: SessionService,
  ) {}

  ngOnInit(): void {
    const rol = String(this.session.getRol() || '').trim().toUpperCase();
    this.puedeVerGlobal = ROLES_CON_ALCANCE_GLOBAL.has(rol);
    this.puedeConsultarVista = ROLES_PILOTO_V2.has(rol);
    if (!this.puedeConsultarVista) {
      this.error = 'La nueva consulta de Inventarios todavía no está habilitada para este perfil.';
      return;
    }

    // El backend define el alcance autorizado incluso si no enviamos sucursal_id.
    // "global" en un perfil limitado NO equivale a acceso global.
    if (this.puedeVerGlobal) this.cargarSucursales();
    this.cargarExistencias();
  }

  ngOnDestroy(): void {
    this.versionConsulta++;
    this.peticionExistencias?.unsubscribe();
    this.peticionSucursales?.unsubscribe();
  }

  cargarSucursales(): void {
    this.peticionSucursales?.unsubscribe();
    this.peticionSucursales = this.inventarioService.listarSucursales().subscribe({
      next: (data: SucursalInventario[]) => {
        this.sucursales = Array.isArray(data)
          ? data.filter(s => !['corporativo', 'administrador'].includes(
            String(s.sucursal || '').trim().toLowerCase(),
          ))
          : [];
      },
      error: () => {
        this.sucursales = [];
      },
    });
  }

  cargarExistencias(): void {
    if (!this.puedeConsultarVista) return;
    this.peticionExistencias?.unsubscribe();
    const versionActual = ++this.versionConsulta;
    this.loading = true;
    this.error = '';
    this.limpiarDatos();

    const sucursalId = this.puedeVerGlobal && this.sucursalSeleccionada !== 'global'
      ? Number(this.sucursalSeleccionada)
      : null;

    this.peticionExistencias = this.inventarioService.verExistencias(
      sucursalId !== null ? { sucursal_id: sucursalId } : undefined,
    ).subscribe({
      next: (data: ExistenciaInventario[]) => {
        if (versionActual !== this.versionConsulta) return;
        this.existencias = Array.isArray(data) ? data : [];
        this.actualizarResumen();
        this.aplicarFiltros();
        this.loading = false;
      },
      error: (err: any) => {
        if (versionActual !== this.versionConsulta) return;
        this.limpiarDatos();
        this.error = err?.status === 403
          ? 'No tienes permiso para consultar las existencias de esta sucursal.'
          : 'No fue posible consultar las existencias. Intenta nuevamente.';
        this.loading = false;
      },
    });
  }

  onSucursalChange(nuevaSucursal: number | 'global'): void {
    this.sucursalSeleccionada = nuevaSucursal;
    this.busqueda = '';
    this.categoriaSeleccionada = 'todas';
    this.familiaSeleccionada = 'todas';
    this.estadoStock = 'todos';
    this.cargarExistencias();
  }

  onCategoriaChange(nuevaCategoria: string): void {
    this.categoriaSeleccionada = nuevaCategoria;
    // La categoría es autoritativa: descartar una familia incompatible.
    if (nuevaCategoria !== 'todas' && this.familiaSeleccionada !== 'todas' &&
        !this.existencias.some(item =>
          this.nombreCategoria(item) === nuevaCategoria &&
          this.nombreFamilia(item) === this.familiaSeleccionada)) {
      this.familiaSeleccionada = 'todas';
    }
    this.quitarFamiliaRedundante();
    this.aplicarFiltros();
  }

  onFamiliaChange(nuevaFamilia: string): void {
    this.familiaSeleccionada = nuevaFamilia;
    if (nuevaFamilia !== 'todas') {
      // Inferir la categoría sólo si todos los registros de la familia
      // pertenecen inequívocamente a una sola. «Sin familia» podría
      // encontrarse tanto en Cardio como en el catálogo pendiente.
      const categoriasDeFamilia = new Set(
        this.existencias
          .filter(item => this.nombreFamilia(item) === nuevaFamilia)
          .map(item => this.nombreCategoria(item)),
      );
      if (categoriasDeFamilia.size === 1) {
        this.categoriaSeleccionada = [...categoriasDeFamilia][0];
      } else if (this.categoriaSeleccionada !== 'todas' &&
                 !categoriasDeFamilia.has(this.categoriaSeleccionada)) {
        this.categoriaSeleccionada = 'todas';
      }
    }
    this.quitarFamiliaRedundante();
    this.aplicarFiltros();
  }

  private quitarFamiliaRedundante(): void {
    if (this.categoriaSeleccionada === 'todas' || this.familiaSeleccionada === 'todas') return;
    const registrosCategoria = this.existencias.filter(item =>
      this.nombreCategoria(item) === this.categoriaSeleccionada);
    // Un filtro que coincide con TODOS los registros de su categoría
    // no aporta precisión. No conservarlo oculto en el estado.
    if (registrosCategoria.length && registrosCategoria.every(item =>
      this.nombreFamilia(item) === this.familiaSeleccionada)) {
      this.familiaSeleccionada = 'todas';
    }
  }

  aplicarFiltros(): void {
    this.actualizarOpcionesCruzadas();
    const termino = this.normalizar(this.busqueda);
    this.existenciasFiltradas = this.existencias.filter(item => {
      const categoria = this.nombreCategoria(item);
      const familia = this.nombreFamilia(item);
      const conStock = Number(item.stock ?? 0) > 0;
      if (this.categoriaSeleccionada !== 'todas' && categoria !== this.categoriaSeleccionada) {
        return false;
      }
      if (this.familiaSeleccionada !== 'todas' && familia !== this.familiaSeleccionada) {
        return false;
      }
      if (this.estadoStock === 'con-stock' && !conStock) return false;
      if (this.estadoStock === 'sin-stock' && conStock) return false;
      if (!termino) return true;

      return [
        item.nombre, item.codigo_interno, item.tipo, item.marca,
        item.proveedor, item.categoria, item.subcategoria,
        item.categoria_catalogo, categoria, familia,
        item.sucursal_nombre, item.inventario_id,
      ].some(valor => this.normalizar(valor).includes(termino));
    });
    this.paginaActual = 0;
    this.actualizarPagina();
  }

  limpiarFiltros(): void {
    this.busqueda = '';
    this.categoriaSeleccionada = 'todas';
    this.familiaSeleccionada = 'todas';
    this.estadoStock = 'todos';
    this.aplicarFiltros();
  }

  irPagina(indice: number): void {
    if (indice < 0 || indice >= this.totalPaginas) return;
    this.paginaActual = indice;
    this.actualizarPagina();
  }

  get totalPaginas(): number {
    return Math.max(1, Math.ceil(this.existenciasFiltradas.length / this.pageSize));
  }

  get rangoInicio(): number {
    return this.existenciasFiltradas.length === 0 ? 0 : this.paginaActual * this.pageSize + 1;
  }

  get rangoFin(): number {
    return Math.min((this.paginaActual + 1) * this.pageSize, this.existenciasFiltradas.length);
  }

  get hayFiltros(): boolean {
    return !!this.busqueda.trim() ||
      this.categoriaSeleccionada !== 'todas' ||
      this.familiaSeleccionada !== 'todas' ||
      this.estadoStock !== 'todos';
  }

  private actualizarOpcionesCruzadas(): void {
    // Cada selector se calcula con el OTRO selector activo: jamás ofrece
    // Peso Libre bajo Cardio ni familias de gimnasio en dispositivos.
    // Se conserva el dataset autorizado completo para los KPIs superiores.
    const categoriasCompatibles = new Set<string>();
    const familiasCompatibles = new Set<string>();
    for (const item of this.existencias) {
      const categoria = this.nombreCategoria(item);
      const familia = this.nombreFamilia(item);
      if (this.familiaSeleccionada === 'todas' || familia === this.familiaSeleccionada) {
        categoriasCompatibles.add(categoria);
      }
      if (familia !== null &&
          (this.categoriaSeleccionada === 'todas' || categoria === this.categoriaSeleccionada)) {
        familiasCompatibles.add(familia);
      }
    }
    this.categoriasDisponibles = this.categorias.filter(categoria =>
      categoriasCompatibles.has(categoria));
    this.familiasDisponibles = this.familias.filter(familia =>
      familiasCompatibles.has(familia));

    const universoCategoria = this.categoriaSeleccionada === 'todas'
      ? this.existencias
      : this.existencias.filter(item =>
          this.nombreCategoria(item) === this.categoriaSeleccionada);
    // Mostrar Familia solamente cuando permita acotar el universo visible:
    // dos o más familias, o una familia junto con registros sin ella.
    this.mostrarFiltroFamilia = this.familiasDisponibles.length > 0 &&
      (this.familiasDisponibles.length > 1 || universoCategoria.some(item =>
        this.nombreFamilia(item) !== this.familiasDisponibles[0]));
  }

  private actualizarPagina(): void {
    const inicio = this.paginaActual * this.pageSize;
    this.filasPagina = this.existenciasFiltradas.slice(inicio, inicio + this.pageSize);
  }

  private actualizarResumen(): void {
    this.totalReferencias = this.existencias.length;
    this.referenciasConStock = this.existencias.filter(e => Number(e.stock ?? 0) > 0).length;
    this.referenciasSinStock = this.totalReferencias - this.referenciasConStock;

    const porCategoria = new Map<string, number>();
    for (const item of this.existencias) {
      const categoria = this.nombreCategoria(item);
      porCategoria.set(categoria, (porCategoria.get(categoria) || 0) + 1);
    }
    this.categorias = [...porCategoria.keys()].sort((a, b) => a.localeCompare(b, 'es'));
    this.totalCategorias = this.categorias.length;
    const orden = [...porCategoria.entries()].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0], 'es'));
    // Mostrar todas las categorias reales del alcance actual (7 en global).
    // Sólo consolidar en «Otras» si hubiera más de ocho categorías.
    const principales = orden.slice(0, 8);
    const otras = orden.slice(8).reduce((total, [, cantidad]) => total + cantidad, 0);
    if (otras) principales.push(['Otras categorías', otras]);

    this.composicion = principales.map(([nombre, cantidad], indice) => ({
      nombre,
      cantidad,
      porcentaje: this.totalReferencias ? cantidad / this.totalReferencias * 100 : 0,
      color: 'category-' + indice,
    }));

    // Sólo los aparatos necesitan una familia de Mantenimiento.
    // Dispositivos de recepción/gerencia sin familia NO son pendientes.
    const aparatos = this.existencias.filter(item => this.esAparato(item));
    this.totalEquiposGimnasio = aparatos.length;
    const porFamilia = new Map<string, number>();
    for (const item of aparatos) {
      const familia = this.nombreFamilia(item)!;
      porFamilia.set(familia, (porFamilia.get(familia) || 0) + 1);
    }
    this.equiposSinFamilia = porFamilia.get('Sin familia') || 0;
    this.familias = [...porFamilia.keys()].sort((a, b) => a.localeCompare(b, 'es'));
    this.composicionFamilias = [...porFamilia.entries()]
      .sort((a, b) => (
        a[0] === 'Sin familia' ? 1 : b[0] === 'Sin familia' ? -1 :
        b[1] - a[1] || a[0].localeCompare(b[0], 'es')
      ))
      .map(([nombre, cantidad]) => ({
        nombre, cantidad, sinClasificar: nombre === 'Sin familia',
      }));
  }

  private limpiarDatos(): void {
    this.existencias = [];
    this.existenciasFiltradas = [];
    this.filasPagina = [];
    this.categorias = [];
    this.categoriasDisponibles = [];
    this.composicion = [];
    this.familias = [];
    this.familiasDisponibles = [];
    this.mostrarFiltroFamilia = false;
    this.composicionFamilias = [];
    this.totalEquiposGimnasio = 0;
    this.equiposSinFamilia = 0;
    this.totalReferencias = 0;
    this.referenciasConStock = 0;
    this.referenciasSinStock = 0;
    this.totalCategorias = 0;
    this.paginaActual = 0;
  }

  // Prioridad: categoría de catálogo. En aparatos legados sin vínculo NO
  // presumimos que el texto libre (Maquinas/Cardio) sea catálogo oficial.
  nombreCategoria(item: ExistenciaInventario): string {
    const catalogo = String(item.categoria_catalogo || '').trim();
    if (catalogo) return catalogo;
    if (this.esAparato(item)) return 'Sin categoría de catálogo';
    return String(item.categoria || '').trim() || 'Sin categoría';
  }

  nombreFamilia(item: ExistenciaInventario): string | null {
    if (!this.esAparato(item)) return null;
    return String(item.familia_equipo?.nombre || '').trim() || 'Sin familia';
  }

  formatoPorcentaje(porcentaje: number): string {
    if (porcentaje > 0 && porcentaje < 1) return '<1%';
    return Math.round(porcentaje) + '%';
  }

  private esAparato(item: ExistenciaInventario): boolean {
    const tipo = this.normalizar(item.tipo);
    return tipo === 'aparato' || tipo === 'aparatos';
  }

  private normalizar(valor: unknown): string {
    return String(valor ?? '').normalize('NFD').replace(/[\u0300-\u036f]/g, '')
      .trim().toLocaleLowerCase('es');
  }
}
