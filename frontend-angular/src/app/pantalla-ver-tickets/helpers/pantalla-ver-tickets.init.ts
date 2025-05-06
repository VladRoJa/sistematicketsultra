// C:\Users\Vladimir\Documents\Sistema tickets\frontend-angular\src\app\pantalla-ver-tickets\helpers\pantalla-ver-tickets.init.ts


import { PantallaVerTicketsComponent, ApiResponse, Ticket } from '../pantalla-ver-tickets.component';
import { HttpHeaders } from '@angular/common/http';
import { formatearFecha, generarOpcionesDisponiblesDesdeTickets, regenerarFiltrosFiltradosDesdeTickets, formatearFechaFinalizado } from '../../utils/ticket-utils';
import { environment } from 'src/environments/environment';

export async function obtenerUsuarioAutenticado(component: PantallaVerTicketsComponent): Promise<void> {
  const token = localStorage.getItem('token');
  if (!token) return;

  const headers = new HttpHeaders({
    'Authorization': `Bearer ${token}`,
    'Content-Type': 'application/json'
  });

  try { 
    const data = await component.http.get<{ user: any }>(`${environment.apiUrl}/auth/session-info`, { headers }).toPromise();
    if (data?.user) {
      component.user = data.user;
      component.usuarioEsAdmin = (component.user.sucursal_id === 1000);
      component.changeDetectorRef.detectChanges(); // 👈 OBLIGA a que se re-renderice el HTML
    }
  } catch (error) {
    console.error("❌ Error obteniendo usuario autenticado:", error);
  }
}


export function cargarTickets(component: PantallaVerTicketsComponent): void {
  component.loading = true;

  // Cargar 100 tickets máximo
  component.ticketService.getTickets(100, 0).subscribe({
    next: (data: ApiResponse) => {
      const ticketsProcesados = data.tickets.map(ticket => ({
        ...ticket,
        fecha_creacion_original: ticket.fecha_creacion,
        fecha_finalizado_original: ticket.fecha_finalizado,
        criticidad: ticket.criticidad || 1,
        estado: ticket.estado?.toLowerCase().trim(),
        departamento: component.departamentoService.obtenerNombrePorId(ticket.departamento_id),
        fecha_creacion: ticket.fecha_creacion && ticket.fecha_creacion !== 'N/A' ? formatearFecha(ticket.fecha_creacion) : null,
        fecha_finalizado: ticket.fecha_finalizado && ticket.fecha_finalizado !== 'N/A' ? formatearFechaFinalizado(ticket.fecha_finalizado) : null,
        historial_fechas: typeof ticket.historial_fechas === "string"
          ? JSON.parse(ticket.historial_fechas)
          : ticket.historial_fechas || []
      }));

      component.ticketsCompletos = [...ticketsProcesados];
      component.tickets = [...ticketsProcesados];
      component.filteredTickets = [...ticketsProcesados];
      component.page = 1;
      component.totalTickets = ticketsProcesados.length;
      component.totalPagesCount = Math.ceil(component.totalTickets / component.itemsPerPage);
      actualizarVisibleTickets(component);

      // 🆕 Generar listas "Disponibles" desde los tickets
      component.categoriasDisponibles = generarOpcionesDisponiblesDesdeTickets(ticketsProcesados, 'categoria');
      component.descripcionesDisponibles = generarOpcionesDisponiblesDesdeTickets(ticketsProcesados, 'descripcion');
      component.usuariosDisponibles = generarOpcionesDisponiblesDesdeTickets(ticketsProcesados, 'username');
      component.estadosDisponibles = generarOpcionesDisponiblesDesdeTickets(ticketsProcesados, 'estado');
      component.criticidadesDisponibles = generarOpcionesDisponiblesDesdeTickets(ticketsProcesados, 'criticidad');
      component.departamentosDisponibles = generarOpcionesDisponiblesDesdeTickets(ticketsProcesados, 'departamento');
      component.subcategoriasDisponibles = generarOpcionesDisponiblesDesdeTickets(ticketsProcesados, 'subcategoria');
      component.detallesDisponibles = generarOpcionesDisponiblesDesdeTickets(ticketsProcesados, 'subsubcategoria');


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
        component
      );

      // 🔄 Asegurar que se muestren los checkboxes filtrables
      component.categoriasFiltradas = [...component.categoriasDisponibles];
      component.descripcionesFiltradas = [...component.descripcionesDisponibles];
      component.usuariosFiltrados = [...component.usuariosDisponibles];
      component.estadosFiltrados = [...component.estadosDisponibles];
      component.criticidadesFiltradas = [...component.criticidadesDisponibles];
      component.departamentosFiltrados = [...component.departamentosDisponibles];
      component.subcategoriasFiltradas = [...component.subcategoriasDisponibles];
      component.detallesFiltrados = [...component.detallesDisponibles];

      component.loading = false;
    },
    error: () => {
      component.loading = false;
      console.error("❌ Error cargando tickets.");
    }
  });
}

export function actualizarVisibleTickets(component: PantallaVerTicketsComponent): void {
  const start = (component.page - 1) * component.itemsPerPage;
  const end = start + component.itemsPerPage;
  component.visibleTickets = component.filteredTickets.slice(start, end);
}

export function ordenar(columna: keyof Ticket, direccion: 'asc' | 'desc') {
  this.filteredTickets.sort((a, b) => {
    const valorA = (a[columna] ?? '').toString().toLowerCase();
    const valorB = (b[columna] ?? '').toString().toLowerCase();

    if (valorA < valorB) return direccion === 'asc' ? -1 : 1;
    if (valorA > valorB) return direccion === 'asc' ? 1 : -1;
    return 0;
  });

  actualizarVisibleTickets(this);
}


export function actualizarDiasConTicketsFinalizado(component: PantallaVerTicketsComponent): void {
  const fechasSet = new Set<string>();
  component.ticketsPorDiaFinalizado = {};

  for (const ticket of component.filteredTickets) {
    if (ticket.fecha_finalizado) {
      const fecha = new Date(ticket.fecha_finalizado);
      if (!isNaN(fecha.getTime())) {
        const isoDate = fecha.toISOString().split('T')[0];
        fechasSet.add(isoDate);
        component.ticketsPorDiaFinalizado[isoDate] = (component.ticketsPorDiaFinalizado[isoDate] || 0) + 1;
      }
    }
  }

  component.diasConTicketsFinalizado = fechasSet;
}

export function actualizarDiasConTicketsCreacion(component: PantallaVerTicketsComponent): void {
  component.diasConTicketsCreacion = new Set();
  component.ticketsPorDiaCreacion = {};

  for (const ticket of component.filteredTickets) {
    const fecha = ticket.fecha_creacion_original?.split('T')[0];
    if (fecha) {
      component.diasConTicketsCreacion.add(fecha);
      component.ticketsPorDiaCreacion[fecha] = (component.ticketsPorDiaCreacion[fecha] || 0) + 1;
    }
  }
}

