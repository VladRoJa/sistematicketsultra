/** Nombres orientados a operación para el catálogo histórico (40 claves).
 * SOLO PRESENTACIÓN: jamás interpretar estos textos como decisiones de autorización.
 * Las claves full_key, los guards y las estimaciones siguen siendo fuente separada.
 */
export interface PermissionActionPresentation {
  label: string;
  explanation: string;
  purpose: string;
}

const ACTION_ALIASES: Readonly<Record<string, PermissionActionPresentation>> = {
  'tickets.view': { label: "Consultar tickets", explanation: "Ver la bandeja de tickets y la información disponible según el alcance del usuario.", purpose: "Consultar" },
  'tickets.create': { label: "Crear tickets", explanation: "Registrar una nueva solicitud o incidencia operativa.", purpose: "Crear" },
  'tickets.update': { label: "Editar datos de tickets", explanation: "Modificar información general de tickets existentes.", purpose: "Modificar" },
  'tickets.update_status': { label: "Cambiar estado de tickets", explanation: "Actualizar el estado de atención de un ticket.", purpose: "Modificar" },
  'tickets.close': { label: "Cerrar o validar tickets", explanation: "Realizar las acciones de cierre o validación aplicables a un ticket.", purpose: "Validar" },
  'tickets.notify': { label: "Enviar avisos de tickets", explanation: "Generar notificaciones relacionadas con la atención de tickets.", purpose: "Comunicar" },
  'tickets.delete_all': { label: "Eliminar todos los tickets", explanation: "Operación masiva excepcional para eliminar tickets; está sujeta a controles adicionales.", purpose: "Administrar" },
  'tickets.maintenance.coordinate': { label: "Coordinar atención de mantenimiento", explanation: "Asignar personal o proveedor y registrar fecha compromiso en tickets de mantenimiento.", purpose: "Coordinar" },
  'tickets.maintenance.read_assigned_only': { label: "Limitar vista a tickets asignados", explanation: "Restricción: la bandeja de mantenimiento muestra únicamente tickets asignados al usuario.", purpose: "Restringir" },
  'inventory.read': { label: "Consultar inventario y existencias", explanation: "Revisar artículos, equipos y existencias registradas.", purpose: "Consultar" },
  'inventory.master_write': { label: "Administrar inventario general", explanation: "Crear, modificar, importar o eliminar registros del inventario maestro.", purpose: "Administrar" },
  'inventory.movement_write': { label: "Registrar movimientos de inventario", explanation: "Registrar o eliminar movimientos que afectan las existencias.", purpose: "Registrar" },
  'pm.read': { label: "Consultar mantenimiento preventivo", explanation: "Revisar bitácoras, programación, historial y calendario de preventivos.", purpose: "Consultar" },
  'pm.execute': { label: "Registrar mantenimiento preventivo", explanation: "Capturar la ejecución y bitácora de actividades preventivas.", purpose: "Registrar" },
  'pm.validate': { label: "Validar mantenimiento preventivo", explanation: "Registrar validaciones de actividades preventivas realizadas.", purpose: "Validar" },
  'pm.configure': { label: "Configurar mantenimiento preventivo", explanation: "Definir o modificar las configuraciones y programación preventiva.", purpose: "Configurar" },
  'warehouse.view': { label: "Consultar reportes de Warehouse", explanation: "Ver reportes cargados, documentos y snapshots disponibles.", purpose: "Consultar" },
  'warehouse.upload': { label: "Cargar reportes a Warehouse", explanation: "Subir archivos y reportes para su resguardo y procesamiento.", purpose: "Cargar" },
  'warehouse.archive': { label: "Archivar reportes de Warehouse", explanation: "Archivar o desactivar cargas documentales almacenadas.", purpose: "Administrar" },
  'warehouse.catalogs': { label: "Administrar catálogos de Warehouse", explanation: "Consultar o modificar catálogos operativos y comerciales del Warehouse.", purpose: "Administrar" },
  'internal_documents.view': { label: "Consultar Nube Corporativa", explanation: "Ver documentos internos que sean visibles para el usuario; cada documento puede tener reglas adicionales.", purpose: "Consultar" },
  'internal_documents.manage': { label: "Administrar Nube Corporativa", explanation: "Crear, modificar, publicar, archivar y configurar visibilidad de documentos internos.", purpose: "Administrar" },
  'track.read': { label: "Consultar indicadores de Track", explanation: "Ver tableros, mart diario y consultas de inteligencia de negocio.", purpose: "Consultar" },
  'track.run_daily_pipeline': { label: "Ejecutar actualización diaria de Track", explanation: "Iniciar manualmente el proceso de actualización del mart diario de Track.", purpose: "Ejecutar" },
  'track.run_agregadoras': { label: "Ejecutar integración de agregadoras", explanation: "Iniciar la integración manual de ingresos de agregadoras con Track.", purpose: "Ejecutar" },
  'planning.read': { label: "Consultar metas y planeación", explanation: "Revisar modelos, lotes de trabajo y metas comerciales.", purpose: "Consultar" },
  'planning.edit': { label: "Modificar metas y planeación", explanation: "Editar modelos o registros de metas en planeación.", purpose: "Modificar" },
  'planning.submit': { label: "Enviar metas a revisión", explanation: "Presentar un conjunto de metas para su revisión.", purpose: "Enviar" },
  'planning.approve': { label: "Aprobar o rechazar metas", explanation: "Revisar y resolver propuestas de metas pendientes.", purpose: "Validar" },
  'planning.publish': { label: "Publicar metas aprobadas", explanation: "Enviar las metas publicadas a la fuente operativa correspondiente.", purpose: "Publicar" },
  'planning.configure_model': { label: "Configurar modelos de metas", explanation: "Definir o modificar los modelos utilizados para planear objetivos.", purpose: "Configurar" },
  'openings.read': { label: "Consultar proyectos de apertura", explanation: "Revisar proyectos, fases y tareas de nuevas aperturas.", purpose: "Consultar" },
  'openings.manage': { label: "Administrar proyectos de apertura", explanation: "Crear, modificar o eliminar proyectos y tareas de aperturas.", purpose: "Administrar" },
  'openings.comment': { label: "Comentar tareas de apertura", explanation: "Agregar comentarios a las tareas de apertura.", purpose: "Comunicar" },
  'catalogs.view': { label: "Consultar catálogos del sistema", explanation: "Acceder a la consulta de catálogos maestros del sistema.", purpose: "Consultar" },
  'catalogs.manage': { label: "Administrar catálogos del sistema", explanation: "Crear, modificar, importar o eliminar registros de catálogos.", purpose: "Administrar" },
  'users.view': { label: "Consultar usuarios del sistema", explanation: "Acceder a la consulta de usuarios y su información.", purpose: "Consultar" },
  'users.manage': { label: "Administrar usuarios y sucursales", explanation: "Crear, modificar o eliminar usuarios y gestionar asignaciones de sucursal.", purpose: "Administrar" },
  'reports.read': { label: "Consultar reportes operativos", explanation: "Revisar reportes de operación disponibles.", purpose: "Consultar" },
  'reports.create_error_report': { label: "Reportar errores operativos", explanation: "Registrar un reporte de error o incidencia operativa.", purpose: "Registrar" },
};

export function permissionActionLabel(key: string | null | undefined, fallback?: string | null): string {
  return (key && ACTION_ALIASES[key]?.label) || fallback?.trim() || key || 'Acción sin identificar';
}

export function permissionActionExplanation(
  key: string | null | undefined, fallback?: string | null,
): string {
  return (key && ACTION_ALIASES[key]?.explanation) || fallback?.trim()
    || 'Descripción pendiente de validar para esta acción del catálogo.';
}

export function permissionActionPurpose(key: string | null | undefined): string {
  return (key && ACTION_ALIASES[key]?.purpose) || 'Sin clasificar';
}
