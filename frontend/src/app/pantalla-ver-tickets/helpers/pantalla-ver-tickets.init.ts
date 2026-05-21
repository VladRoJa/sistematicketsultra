// frontend-angular/src/app/pantalla-ver-tickets/helpers/pantalla-ver-tickets.init.ts

import { HttpHeaders } from '@angular/common/http';
import {
  PantallaVerTicketsComponent,
  ApiResponse,
  Ticket,
} from '../pantalla-ver-tickets.component';
import {
  buscarAncestroNivel,
  regenerarFiltrosFiltradosDesdeTickets,
} from '../../utils/ticket-utils';
import { environment } from 'src/environments/environment';

export async function obtenerUsuarioAutenticado(
  component: PantallaVerTicketsComponent
): Promise<void> {
  const token = localStorage.getItem('token');
  if (!token) {
    return;
  }

  const headers = new HttpHeaders({
    Authorization: `Bearer ${token}`,
    'Content-Type': 'application/json',
  });

  try {
    const data = await component.http
      .get<{ user: any }>(`${environment.apiUrl}/auth/session-info`, { headers })
      .toPromise();

    if (data?.user) {
      component.user = data.user;

      component.usuarioEsAdmin = component.user.sucursal_id === 1000;

      component.usuarioEsEditorCorporativo =
        component.user.sucursal_id === 100 &&
        component.user.rol !== 'ADMINISTRADOR';

      component.changeDetectorRef.detectChanges();
    }
  } catch (error) {
    console.error('❌ Error obteniendo usuario autenticado:', error);
  }
}

function resolverNombreSucursalTicket(
  ticket: any,
  component: PantallaVerTicketsComponent
): string {
  const nombreDirecto =
    ticket.sucursal_nombre_destino ||
    ticket.sucursal_nombre ||
    ticket.sucursal_destino?.sucursal ||
    ticket.sucursal_destino?.nombre ||
    ticket.sucursal?.sucursal ||
    ticket.sucursal?.nombre;

  if (nombreDirecto) {
    return String(nombreDirecto);
  }

  const idRaw =
    ticket.sucursal_id_destino ??
    ticket.sucursal_destino_id ??
    ticket.sucursal_id ??
    ticket.id_sucursal ??
    ticket.sucursal;

  const id = Number(idRaw);

  if (Number.isFinite(id)) {
    return component.sucursalIdNombreMap[id] || String(id);
  }

  return idRaw != null ? String(idRaw) : '—';
}

export function cargarTickets(component: PantallaVerTicketsComponent): void {
  component.loading = true;

  const departamentoScopeId = component.getSelectedDepartmentScopeId();

  const ticketsRequest$ = component.ticketService.getTicketsConFiltros({
    year: component.selectedTicketYear,
    ...(departamentoScopeId ? { departamento_id: departamentoScopeId } : {}),
    no_paging: true,
  });

  ticketsRequest$.subscribe({
    next: (data: ApiResponse) => {
      const ticketsProcesados = data.tickets.map((ticket: Ticket) => {
        const clasificacionId = Number(ticket.clasificacion_id);
        const tieneClasificacionValida = Number.isFinite(clasificacionId);

        const catNivel2 = tieneClasificacionValida
          ? buscarAncestroNivel(clasificacionId, 2, component.categoriasCatalogo)
          : null;

        const catNivel3 = tieneClasificacionValida
          ? buscarAncestroNivel(clasificacionId, 3, component.categoriasCatalogo)
          : null;

        const catNivel4 = tieneClasificacionValida
          ? buscarAncestroNivel(clasificacionId, 4, component.categoriasCatalogo)
          : null;

        return {
          ...ticket,

          fecha_creacion_original: ticket.fecha_creacion,
          fecha_finalizado_original: ticket.fecha_finalizado,

          criticidad: ticket.criticidad || 1,
          estado: (ticket.estado || '').toLowerCase().trim(),

          departamento:
            ticket.departamento_nombre ??
            component.departamentoService.obtenerNombrePorId(ticket.departamento_id) ??
            ticket.departamento,

          fecha_creacion:
            ticket.fecha_creacion !== 'N/A' ? ticket.fecha_creacion : null,

          fecha_en_progreso:
            ticket.fecha_en_progreso && ticket.fecha_en_progreso !== 'N/A'
              ? ticket.fecha_en_progreso
              : null,

          fecha_finalizado:
            ticket.fecha_finalizado !== 'N/A' ? ticket.fecha_finalizado : null,

          historial_fechas:
            typeof ticket.historial_fechas === 'string'
              ? JSON.parse(ticket.historial_fechas)
              : ticket.historial_fechas || [],

          categoria_nivel2: catNivel2,
          subcategoria_nivel3: catNivel3,
          detalle_nivel4: catNivel4,

          categoria: ticket.categoria ?? catNivel2?.nombre ?? '—',
          subcategoria: ticket.subcategoria ?? catNivel3?.nombre ?? '—',
          detalle: ticket.detalle ?? catNivel4?.nombre ?? '—',

          sucursal: resolverNombreSucursalTicket(ticket, component),
        };
      });

      component.ticketsCompletos = [...ticketsProcesados];
      component.tickets = [...ticketsProcesados];

      let base = [...ticketsProcesados];

      if (component.ocultarFinalizados) {
        base = base.filter(
          (ticket) => (ticket.estado || '').toLowerCase() !== 'finalizado'
        );
      }

      component.departamentosDisponibles = Array.from(
        new Set(base.map((ticket) => `${ticket.departamento_id}|${ticket.departamento}`))
      )
        .filter((raw) => raw.split('|')[0] && raw.split('|')[0] !== 'null')
        .map((raw) => {
          const [valor, etiqueta] = raw.split('|');

          return {
            valor: Number(valor),
            etiqueta: etiqueta || valor,
            seleccionado: true,
          };
        });

      component.departamentosFiltrados = [...component.departamentosDisponibles];
      component.temporalSeleccionados['departamento'] = [
        ...component.departamentosDisponibles,
      ];

      const idsNivel2 = Array.from(
        new Set(
          base
            .map((ticket) => ticket.categoria_nivel2?.id)
            .filter((id): id is number => id !== undefined && id !== null)
        )
      );

      const idsNivel3 = Array.from(
        new Set(
          base
            .map((ticket) => ticket.subcategoria_nivel3?.id)
            .filter((id): id is number => id !== undefined && id !== null)
        )
      );

      const idsNivel4 = Array.from(
        new Set(
          base
            .map((ticket) => ticket.detalle_nivel4?.id)
            .filter((id): id is number => id !== undefined && id !== null)
        )
      );

      component.categoriasDisponibles = component.categoriasCatalogo
        .filter((cat) => cat.nivel === 2 && idsNivel2.includes(cat.id))
        .map((cat) => ({
          valor: cat.id,
          etiqueta: cat.nombre ?? String(cat.id),
          seleccionado: true,
        }));

      component.subcategoriasDisponibles = component.categoriasCatalogo
        .filter((cat) => cat.nivel === 3 && idsNivel3.includes(cat.id))
        .map((cat) => ({
          valor: cat.id,
          etiqueta: cat.nombre ?? String(cat.id),
          seleccionado: true,
        }));

      component.detallesDisponibles = component.categoriasCatalogo
        .filter((cat) => cat.nivel === 4 && idsNivel4.includes(cat.id))
        .map((cat) => ({
          valor: cat.id,
          etiqueta: cat.nombre ?? String(cat.id),
          seleccionado: true,
        }));

      component.categoriasFiltradas = [...component.categoriasDisponibles];
      component.subcategoriasFiltradas = [...component.subcategoriasDisponibles];
      component.detallesFiltrados = [...component.detallesDisponibles];

      if (!component.temporalSeleccionados['categoria']) {
        component.temporalSeleccionados['categoria'] = [];
      }

      if (!component.temporalSeleccionados['subcategoria']) {
        component.temporalSeleccionados['subcategoria'] = [];
      }

      if (!component.temporalSeleccionados['detalle']) {
        component.temporalSeleccionados['detalle'] = [];
      }

      component.filteredTickets = [...base];

      component.usuariosDisponibles = extraerUnicosPorCampo(
        component.filteredTickets,
        'username'
      ).map((valor) => ({
        valor,
        seleccionado: true,
      }));

      component.usuariosFiltrados = [...component.usuariosDisponibles];

      if (!component.temporalSeleccionados['username']) {
        component.temporalSeleccionados['username'] = [
          ...component.usuariosDisponibles,
        ];
      }

      component.estadosDisponibles = extraerUnicosPorCampo(
        component.filteredTickets,
        'estado'
      ).map((valor) => ({
        valor,
        seleccionado: true,
      }));

      component.estadosFiltrados = [...component.estadosDisponibles];

      if (!component.temporalSeleccionados['estado']) {
        component.temporalSeleccionados['estado'] = [
          ...component.estadosDisponibles,
        ];
      }

      component.criticidadesDisponibles = extraerUnicosPorCampo(
        component.filteredTickets,
        'criticidad'
      ).map((valor) => ({
        valor,
        seleccionado: true,
      }));

      component.criticidadesFiltradas = [...component.criticidadesDisponibles];

      if (!component.temporalSeleccionados['criticidad']) {
        component.temporalSeleccionados['criticidad'] = [
          ...component.criticidadesDisponibles,
        ];
      }

      component.descripcionesDisponibles = extraerUnicosPorCampo(
        component.filteredTickets,
        'descripcion'
      ).map((valor) => ({
        valor,
        etiqueta: valor,
        seleccionado: true,
      }));

      component.descripcionesFiltradas = [...component.descripcionesDisponibles];

      if (!component.temporalSeleccionados['descripcion']) {
        component.temporalSeleccionados['descripcion'] = [
          ...component.descripcionesDisponibles,
        ];
      }

      const nombresInventarioUnicos = Array.from(
        new Set(component.filteredTickets.map((ticket) => ticket.inventario?.nombre || '—'))
      );

      component.inventariosDisponibles = nombresInventarioUnicos.map((nombre) => ({
        valor: nombre,
        etiqueta: nombre,
        seleccionado: true,
      }));

      component.inventariosFiltrados = [...component.inventariosDisponibles];

      if (!component.temporalSeleccionados['inventario']) {
        component.temporalSeleccionados['inventario'] = [
          ...component.inventariosDisponibles,
        ];
      }

      component.page = 1;
      component.totalTickets = base.length;
      component.totalPagesCount = Math.ceil(
        component.totalTickets / component.itemsPerPage
      );

      actualizarVisibleTickets(component);

      component.categoriasFiltradas = [...component.categoriasDisponibles];
      component.subcategoriasFiltradas = [...component.subcategoriasDisponibles];
      component.detallesFiltrados = [...component.detallesDisponibles];

      component.temporalSeleccionados['categoria'] = [
        ...component.categoriasDisponibles,
      ];
      component.temporalSeleccionados['subcategoria'] = [
        ...component.subcategoriasDisponibles,
      ];
      component.temporalSeleccionados['detalle'] = [
        ...component.detallesDisponibles,
      ];

      regenerarFiltrosFiltradosDesdeTickets(
        component.filteredTickets,
        component.usuariosDisponibles,
        component.estadosDisponibles,
        component.categoriasDisponibles,
        component.descripcionesDisponibles,
        component.criticidadesDisponibles,
        component.departamentosDisponibles,
        component.subcategoriasDisponibles,
        component.detallesDisponibles,
        component.inventariosDisponibles,
        component.sucursalesDisponibles,
        component
      );

      component.categoriasFiltradas = [...component.categoriasDisponibles];
      component.subcategoriasFiltradas = [...component.subcategoriasDisponibles];
      component.detallesFiltrados = [...component.detallesDisponibles];
      component.descripcionesFiltradas = [...component.descripcionesDisponibles];
      component.usuariosFiltrados = [...component.usuariosDisponibles];
      component.estadosFiltrados = [...component.estadosDisponibles];
      component.criticidadesFiltradas = [...component.criticidadesDisponibles];
      component.departamentosFiltrados = [...component.departamentosDisponibles];
      component.inventariosFiltrados = [...component.inventariosDisponibles];

      component.changeDetectorRef.detectChanges();
      component.loading = false;
    },
    error: () => {
      component.loading = false;
      console.error('❌ Error cargando tickets.');
    },
  });
}

export function actualizarVisibleTickets(
  component: PantallaVerTicketsComponent
): void {
  const start = (component.page - 1) * component.itemsPerPage;
  const end = start + component.itemsPerPage;

  component.visibleTickets = component.filteredTickets.slice(start, end);
  component.mostrarAvisoLimite = false;
}

export function ordenar(
  this: PantallaVerTicketsComponent,
  columna: keyof Ticket,
  direccion: 'asc' | 'desc'
): void {
  this.filteredTickets.sort((a: Ticket, b: Ticket) => {
    const valorA = (a[columna] ?? '').toString().toLowerCase();
    const valorB = (b[columna] ?? '').toString().toLowerCase();

    if (valorA < valorB) {
      return direccion === 'asc' ? -1 : 1;
    }

    if (valorA > valorB) {
      return direccion === 'asc' ? 1 : -1;
    }

    return 0;
  });

  actualizarVisibleTickets(this);
}

export function actualizarDiasConTicketsFinalizado(
  component: PantallaVerTicketsComponent
): void {
  const fechasSet = new Set<string>();
  component.ticketsPorDiaFinalizado = {};

  for (const ticket of component.filteredTickets) {
    if (ticket.fecha_finalizado) {
      const fecha = new Date(ticket.fecha_finalizado);

      if (!Number.isNaN(fecha.getTime())) {
        const isoDate = fecha.toISOString().split('T')[0];
        fechasSet.add(isoDate);
        component.ticketsPorDiaFinalizado[isoDate] =
          (component.ticketsPorDiaFinalizado[isoDate] || 0) + 1;
      }
    }
  }

  component.diasConTicketsFinalizado = fechasSet;
}

export function actualizarDiasConTicketsCreacion(
  component: PantallaVerTicketsComponent
): void {
  component.diasConTicketsCreacion = new Set();
  component.ticketsPorDiaCreacion = {};

  for (const ticket of component.filteredTickets) {
    const fecha = ticket.fecha_creacion_original?.split('T')[0];

    if (fecha) {
      component.diasConTicketsCreacion.add(fecha);
      component.ticketsPorDiaCreacion[fecha] =
        (component.ticketsPorDiaCreacion[fecha] || 0) + 1;
    }
  }
}

export function extraerUnicosPorCampo(tickets: any[], campo: string): any[] {
  const set = new Set();

  return tickets
    .map((ticket) => ticket[campo])
    .filter((valor) => {
      if (valor == null || set.has(valor)) {
        return false;
      }

      set.add(valor);
      return true;
    });
}