// C:\Users\Vladimir\Documents\Sistema tickets\frontend-angular\src\app\pantalla-ver-tickets\helpers\pantalla-ver-tickets.departamentos.ts

import { PantallaVerTicketsComponent } from '../pantalla-ver-tickets.component';

/**
 * Cargar los departamentos para el selector de tickets
 */
export function cargarDepartamentos(component: PantallaVerTicketsComponent): void {
  component.departamentoService.obtenerDepartamentos().subscribe({
    next: (data) => {
      component.departamentos = Array.isArray(data) ? data : Object.values(data);
    },
    error: (error) => console.error("❌ Error al obtener departamentos:", error),
  });
}
