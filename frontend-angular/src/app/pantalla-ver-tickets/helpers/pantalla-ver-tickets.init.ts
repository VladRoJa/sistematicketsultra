// frontend-angular\src\app\pantalla-ver-tickets\helpers\pantalla-ver-tickets.init.ts

import { PantallaVerTicketsComponent, ApiResponse, Ticket } from '../pantalla-ver-tickets.component';
import { HttpHeaders } from '@angular/common/http';
import { generarOpcionesCategoriasDesdeTickets, generarOpcionesDisponiblesDesdeTickets, regenerarFiltrosFiltradosDesdeTickets } from '../../utils/ticket-utils';
import { environment } from 'src/environments/environment';
import { hayFiltrosActivos } from './pantalla-ver-tickets.filtros';
import { generarOpcionesClasificacionDesdeTickets, buscarAncestroNivel } from '../../utils/ticket-utils';





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
  
      // 🟢 Admin global
      component.usuarioEsAdmin = (component.user.sucursal_id === 1000);
  
      // 🟦 Editor corporativo (intermedio, puede ver botones de acción)
      component.usuarioEsEditorCorporativo = (
        component.user.sucursal_id === 100 && 
        component.user.rol !== 'ADMINISTRADOR'
      );
  
      // ✅ Detecta cambios después de setear ambos
      component.changeDetectorRef.detectChanges();
    }
  } catch (error) {
    console.error("❌ Error obteniendo usuario autenticado:", error);
  }
}
  

export function cargarTickets(component: PantallaVerTicketsComponent): void {
  component.loading = true;

  component.ticketService.getTickets(100, 0).subscribe({
    next: (data: ApiResponse) => {
      // 1. Procesamos los tickets, agregando referencias a nivel2, nivel3 y nivel4
      const ticketsProcesados = data.tickets.map(ticket => {
        const catNivel2 = buscarAncestroNivel(ticket.clasificacion_id, 2, component.categoriasCatalogo);
        const catNivel3 = buscarAncestroNivel(ticket.clasificacion_id, 3, component.categoriasCatalogo);
        const catNivel4 = buscarAncestroNivel(ticket.clasificacion_id, 4, component.categoriasCatalogo);

        return {
          ...ticket,
          fecha_creacion_original: ticket.fecha_creacion,
          fecha_finalizado_original: ticket.fecha_finalizado,
          criticidad: ticket.criticidad || 1,
          estado: ticket.estado?.toLowerCase().trim(),
          departamento: component.departamentoService.obtenerNombrePorId(ticket.departamento_id),
          fecha_creacion: ticket.fecha_creacion !== 'N/A' ? ticket.fecha_creacion : null,
          fecha_en_progreso: ticket.fecha_en_progreso && ticket.fecha_en_progreso !== 'N/A' ? ticket.fecha_en_progreso : null,
          fecha_finalizado: ticket.fecha_finalizado !== 'N/A' ? ticket.fecha_finalizado : null,
          historial_fechas: typeof ticket.historial_fechas === "string"
            ? JSON.parse(ticket.historial_fechas)
            : ticket.historial_fechas || [],
          categoria_nivel2: catNivel2,
          subcategoria_nivel3: catNivel3,
          detalle_nivel4: catNivel4,
        };
      });


            // ---- Opciones de filtro DEPARTAMENTO ----
      component.departamentosDisponibles = Array.from(
        new Set(ticketsProcesados.map(t => `${t.departamento_id}|${t.departamento}`))
      )
      .filter(raw => raw.split('|')[0] && raw.split('|')[0] !== 'null') // Filtra vacíos/null
      .map(raw => {
        const [valor, etiqueta] = raw.split('|');
        return {
          valor: Number(valor),
          etiqueta: etiqueta || valor,
          seleccionado: true
        };
      });
      component.departamentosFiltrados = [...component.departamentosDisponibles];
      component.temporalSeleccionados['departamento'] = [...component.departamentosDisponibles];


      // --- FILTROS POR CATÁLOGO ---
      // IDs usados por los tickets
      const idsNivel2 = Array.from(new Set(ticketsProcesados.map(t => t.categoria_nivel2?.id).filter(Boolean)));
      const idsNivel3 = Array.from(new Set(ticketsProcesados.map(t => t.subcategoria_nivel3?.id).filter(Boolean)));
      const idsNivel4 = Array.from(new Set(ticketsProcesados.map(t => t.detalle_nivel4?.id).filter(Boolean)));

      // Catálogo nivel 2 (categoría)
      component.categoriasDisponibles = component.categoriasCatalogo
        .filter(cat => cat.nivel === 2 && idsNivel2.includes(cat.id))
        .map(cat => ({
          valor: cat.id,
          etiqueta: cat.nombre,
          seleccionado: true,
        }));

      // Catálogo nivel 3 (subcategoría)
      // 1. LOG antes de filtrar/mapear
      console.log('catalogo:', component.categoriasCatalogo);
      console.log('idsNivel3:', idsNivel3);

      // 2. Mapeo y LOG de cada elemento individual (para ver si cat.nombre viene bien)
      component.subcategoriasDisponibles = component.categoriasCatalogo
        .filter(cat => cat.nivel === 3 && idsNivel3.includes(cat.id))
        .map(cat => {
          console.log('cat:', cat); // <- cada subcategoría encontrada
          return {
            valor: cat.id,
            etiqueta: cat.nombre,
            seleccionado: true,
          };
        });

      // 3. LOG después de mapear todo
      console.log('subcategoriasDisponibles:', component.subcategoriasDisponibles);


      // Catálogo nivel 4 (detalle)
      component.detallesDisponibles = component.categoriasCatalogo
        .filter(cat => cat.nivel === 4 && idsNivel4.includes(cat.id))
        .map(cat => ({
          valor: cat.id,
          etiqueta: cat.nombre,
          seleccionado: true,
        }));

        component.categoriasFiltradas = [...component.categoriasDisponibles];
        component.subcategoriasFiltradas = [...component.subcategoriasDisponibles];
        component.detallesFiltrados = [...component.detallesDisponibles];
        if (!component.temporalSeleccionados['categoria']) component.temporalSeleccionados['categoria'] = [];
        if (!component.temporalSeleccionados['subcategoria']) component.temporalSeleccionados['subcategoria'] = [];
        if (!component.temporalSeleccionados['detalle']) component.temporalSeleccionados['detalle'] = [];




      // El resto igual que antes
      component.ticketsCompletos = [...ticketsProcesados];
      component.tickets = [...ticketsProcesados];
      component.filteredTickets = [...ticketsProcesados];
      component.page = 1;
      component.totalTickets = ticketsProcesados.length;
      component.totalPagesCount = Math.ceil(component.totalTickets / component.itemsPerPage);

      actualizarVisibleTickets(component);



      component.categoriasFiltradas = [...component.categoriasDisponibles];
      component.subcategoriasFiltradas = [...component.subcategoriasDisponibles];
      component.detallesFiltrados = [...component.detallesDisponibles];

      component.temporalSeleccionados['categoria'] = [...component.categoriasDisponibles];
      component.temporalSeleccionados['subcategoria'] = [...component.subcategoriasDisponibles];
      component.temporalSeleccionados['detalle'] = [...component.detallesDisponibles];


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
        component
      );

      // Sincroniza filtrados iniciales
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
      console.error("❌ Error cargando tickets.");
    }
  });
}



export function actualizarVisibleTickets(component: PantallaVerTicketsComponent): void {
  const start = (component.page - 1) * component.itemsPerPage;
  const end = start + component.itemsPerPage;

if (hayFiltrosActivos(component)) {
  component.visibleTickets = component.filteredTickets.slice(0, 100);
  component.mostrarAvisoLimite = component.filteredTickets.length > 100;
} else {
  component.visibleTickets = component.filteredTickets.slice(start, end);
  component.mostrarAvisoLimite = false;
}
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


