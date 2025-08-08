//frontend-angular\src\app\utils\mapa-formularios-tickets.ts


/**
 * Mapea los campos de cada formulario a lo que espera el backend.
 * Puedes modificar aquí los nombres de los campos del form y los que espera el modelo backend.
 */
export const MAPEO_FORMULARIOS: Record<string, { [key: string]: string }> = {
  mantenimiento_aparatos: {
    descripcion: "descripcion",
    categoria: "categoria",
    subcategoria: "subcategoria",
    detalle: "detalle",
    aparato_id: "aparato_id",
    necesita_refaccion: "necesita_refaccion",
    descripcion_refaccion: "descripcion_refaccion",
    criticidad: "criticidad",
    departamento: "departamento_id", // Ojo, departamento_id viene del padre
  },
mantenimiento_edificio: {
  descripcion: "descripcion",
  categoria: "categoria",
  subcategoria: "subcategoria",
  detalle: "detalle",
  ubicacion: "ubicacion",
  equipo: "equipo",
  criticidad: "criticidad",
  departamento: "departamento_id"
},
  compras: {
    descripcion: "descripcion",
    categoria: "categoria",
    subcategoria: "subcategoria",
    detalle: "detalle",
    criticidad: "criticidad",
    departamento: "departamento_id",
  },
  finanzas: {
    descripcion: "descripcion",
    categoria: "categoria",
    subcategoria: "subcategoria",
    detalle: "detalle",
    criticidad: "criticidad",
    departamento: "departamento_id",
  },
  gerencia_deportiva: {
    descripcion: "descripcion",
    categoria: "categoria",
    subcategoria: "subcategoria",
    detalle: "detalle",
    criticidad: "criticidad",
    departamento: "departamento_id",
  },
  marketing: {
    descripcion: "descripcion",
    categoria: "categoria",
    subcategoria: "subcategoria",
    detalle: "detalle",
    criticidad: "criticidad",
    departamento: "departamento_id",
  },
  recursos_humanos: {
    descripcion: "descripcion",
    categoria: "categoria",
    subcategoria: "subcategoria",
    detalle: "detalle",
    criticidad: "criticidad",
    departamento: "departamento_id",
  },
  sistemas: {
    descripcion: "descripcion",
    categoria: "categoria",
    subcategoria: "subcategoria",
    detalle: "detalle",
    aparato_id: "aparato_id",
    criticidad: "criticidad",
    departamento: "departamento_id",
  },
};


/**
 * Transforma el formValue de cualquier subformulario al payload esperado por el backend.
 * 
 * @param formValue El value del FormGroup
 * @param tipoFormulario Uno de los keys definidos en MAPEO_FORMULARIOS, ej: 'compras', 'sistemas', etc.
 */
export function mapearPayloadTicket(formValue: any, tipoFormulario: string): any {
  const mapeo = MAPEO_FORMULARIOS[tipoFormulario];
  if (!mapeo) {
    throw new Error(`No existe mapeo para tipo de formulario: ${tipoFormulario}`);
  }
  const payload: any = {};
  Object.entries(mapeo).forEach(([campoForm, campoBackend]) => {
    if (formValue[campoForm] !== undefined) {
      payload[campoBackend] = formValue[campoForm];
    }
  });
  return payload;
}

export function detectarTipoFormulario(): string {
  const deptoId = this.formularioCrearTicket.value.departamento;
  if (deptoId === 1) {
    const tipoMantenimiento = this.formularioCrearTicket.value.tipoMantenimiento;
    if (tipoMantenimiento === 'aparatos') return 'mantenimiento_aparatos';
    if (tipoMantenimiento === 'edificio') return 'mantenimiento_edificio';
  }
  if (deptoId === 2) return 'finanzas';
  if (deptoId === 3) return 'marketing';
  if (deptoId === 4) return 'gerencia_deportiva';
  if (deptoId === 5) return 'recursos_humanos';
  if (deptoId === 6) return 'compras';
  if (deptoId === 7) return 'sistemas';
  if (deptoId === 8) return 'corporativo';

  return 'otros'; // O el valor por defecto que tú quieras
}