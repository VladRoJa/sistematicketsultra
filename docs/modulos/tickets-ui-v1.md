# Tickets UI v1

## Objetivo

Aplicar Suite Ultra UI v1 a la pantalla principal de Tickets sin alterar la lógica funcional existente.

El primer alcance será mejorar la estructura visual, jerarquía, legibilidad y consistencia del módulo con la nueva identidad Ultra.

---

## Alcance inicial

### Pantalla Ver Tickets

Se aplicará una capa visual nueva a:

- Contenedor principal.
- Header de pantalla.
- Barra de acciones rápidas.
- Panel de filtros unificados.
- Card de tabla.
- Paginación y exportación.
- Colores, bordes, sombras y espaciados usando tokens globales.

---

## No alcance de esta fase

No se modificará:

- Lógica de filtros.
- Helpers TypeScript.
- Endpoints backend.
- Paginación.
- Exportación Excel.
- Acciones de cambio de estado.
- Flujo RRHH.
- Fecha solución.
- Historial.
- Modales.

---

## Reglas de implementación

- No agregar lógica nueva en HTML.
- No mover lógica funcional al template.
- Evitar estilos inline.
- Usar clases CSS.
- Usar tokens globales de Suite Ultra UI v1.
- Mantener los bindings existentes.
- Cambiar estructura visual sin cambiar comportamiento.

---

## Archivos involucrados

```text
frontend/src/app/pantalla-ver-tickets/pantalla-ver-tickets.component.html
frontend/src/app/pantalla-ver-tickets/pantalla-ver-tickets.component.css

```

---

## Crear Ticket UI v1

### Objetivo

Aplicar Suite Ultra UI v1 a la pantalla de creación de tickets sin modificar la lógica funcional existente.

La pantalla debe sentirse parte del mismo sistema visual que Ver Tickets y el nuevo layout principal.

---

### Alcance

Se aplicará una capa visual nueva a:

- Contenedor principal.
- Header de pantalla.
- Card principal del formulario.
- Agrupación visual de campos.
- Campos dinámicos de categoría/niveles.
- Subformularios existentes.
- Selector de criticidad.
- Botón principal de creación.
- Estados de carga.

---

### No alcance

No se modificará:

- Lógica del formulario.
- Validaciones existentes.
- Payload enviado al backend.
- Endpoints.
- Reglas dinámicas por categoría/subcategoría.
- Subformularios de aparatos.
- Subformularios de sistemas.
- Flujo de refacciones.
- Permisos por rol.

---

### Archivos involucrados

```text
frontend/src/app/pantalla-crear-ticket/crear-ticket-refactor.component.html
frontend/src/app/pantalla-crear-ticket/crear-ticket-refactor.component.css
```

---

## Modal Historial de Ticket UI v1

### Objetivo

Aplicar la paleta oficial de Suite Ultra UI v1 al modal de historial/resumen de ticket sin modificar su lógica funcional.

Este modal ya cuenta con una estructura visual mejorada, por lo que el alcance será principalmente ajuste de color, contraste, espaciado menor y consistencia con la identidad Ultra.

### Alcance

- Aplicar tokens globales de Suite Ultra UI v1.
- Reemplazar tonos azules/cyan heredados por Ultra Orange, carbón, grises y superficies suaves.
- Mantener la estructura actual del modal.
- Mantener resumen del ticket.
- Mantener cards informativas.
- Mantener historial de solución.
- Mantener estado vacío.
- Mantener botón de cierre.

### No alcance

- No cambiar inputs del modal.
- No cambiar datos mostrados.
- No cambiar lógica de historial.
- No cambiar formato de fechas.
- No cambiar permisos.
- No cambiar acciones funcionales.

### Validación

Antes del commit debe comprobarse:

- El modal abre correctamente desde Ver Tickets.
- El resumen del ticket se muestra correctamente.
- El estado del ticket se muestra correctamente.
- El historial se muestra si existen registros.
- El estado vacío se muestra si no hay historial.
- El botón Cerrar funciona.

---

## Modal Editar Fecha Solución UI v1

### Objetivo

Aplicar Suite Ultra UI v1 al modal de edición de fecha solución sin modificar la lógica funcional.

Este modal forma parte del flujo de seguimiento de tickets y debe mantener la obligatoriedad de fecha y motivo.

### Alcance

- Aplicar paleta oficial Ultra.
- Mejorar estructura visual del título.
- Mejorar presentación de campos.
- Mejorar botones de acción.
- Mantener datepicker actual.
- Mantener motivo obligatorio.
- Mantener comportamiento de carga.

### No alcance

- No cambiar validaciones.
- No cambiar payload emitido.
- No cambiar formato de fecha.
- No cambiar permisos.
- No cambiar lógica TypeScript.

### Validación

Antes del commit debe comprobarse:

- El modal abre correctamente.
- Precarga la fecha actual si existe.
- No permite guardar sin fecha.
- No permite guardar sin motivo.
- Guardar cierra el modal con fecha y motivo.
- Cancelar cierra sin cambios.

---

## Modal Asignar Fecha Solución UI v1

### Objetivo

Aplicar Suite Ultra UI v1 al modal de asignación de fecha solución sin modificar la lógica funcional.

Este modal se usa cuando se asigna una fecha compromiso al ticket y puede capturar información de refacción cuando el ticket pertenece a Mantenimiento o Sistemas.

### Alcance

- Aplicar paleta oficial Ultra.
- Mejorar estructura visual del título.
- Mejorar campos de fecha y motivo.
- Mejorar bloque opcional de refacción.
- Eliminar estilos inline.
- Mejorar botones de acción.
- Mantener validaciones actuales.
- Mantener outputs actuales.

### No alcance

- No cambiar lógica TypeScript.
- No cambiar payload emitido.
- No cambiar reglas de refacción.
- No cambiar validaciones.
- No cambiar permisos.
- No cambiar flujo de guardado.

### Validación

Antes del commit debe comprobarse:

- El modal abre correctamente.
- No permite guardar sin fecha.
- No permite guardar sin motivo.
- Respeta fecha mínima.
- Muestra bloque de refacción para Mantenimiento/Sistemas.
- Oculta bloque de refacción cuando no aplica.
- Guardar emite fecha, motivo y datos de refacción cuando aplica.
- Cancelar cierra sin cambios.

---

## Diálogo de Confirmación UI v1

### Objetivo

Aplicar Suite Ultra UI v1 al diálogo compartido de confirmación usado por el módulo Tickets.

Este diálogo se utiliza en flujos sensibles como cierre, validación y confirmaciones generales, por lo que el cambio debe ser únicamente visual.

### Alcance

- Aplicar paleta oficial Ultra.
- Mejorar título, mensaje y jerarquía visual.
- Mejorar botones de aceptar/cancelar.
- Mantener `true` al confirmar.
- Mantener `false` al cancelar.
- Mantener compatibilidad con `titulo`, `mensaje`, `textoAceptar` y `textoCancelar`.

### No alcance

- No cambiar lógica TypeScript.
- No cambiar payload de cierre.
- No cambiar permisos.
- No cambiar flujos de tickets.
- No reemplazar todavía el `prompt` de rechazo RRHH.

### Validación

Antes del commit debe comprobarse:

- El diálogo abre correctamente.
- Cancelar devuelve `false`.
- Aceptar devuelve `true`.
- Los textos personalizados siguen funcionando.
- Los flujos de cierre/validación siguen funcionando.

---

## Modal Cierre Ticket UI v1

### Objetivo

Aplicar Suite Ultra UI v1 al modal de cierre de ticket sin modificar su lógica funcional.

Este modal se usa en los flujos de cierre normal y cierre administrativo/gerente. Después del ajuste de flujo, este modal queda como la confirmación principal del cierre.

### Alcance

- Aplicar paleta oficial Ultra.
- Mejorar título del modal.
- Mejorar campo de costo de solución.
- Mejorar campo de notas de cierre.
- Mejorar botones Cancelar / Aceptar.
- Mantener los datos capturados actuales.
- Mantener compatibilidad con los flujos `Finalizar` y `Cierre gerente`.

### No alcance

- No cambiar lógica TypeScript.
- No cambiar payload.
- No cambiar validaciones.
- No cambiar permisos.
- No cambiar backend.
- No reintroducir confirmación secundaria.

### Validación

Antes del commit debe comprobarse:

- El modal abre desde `Finalizar`.
- El modal abre desde `Cierre gerente`.
- El campo costo sigue funcionando.
- El campo notas sigue funcionando.
- Cancelar cierra sin cambios.
- Aceptar continúa el flujo actual.
- No aparece confirmación secundaria después de aceptar.

---

## Diálogo de Confirmación UI v1

### Objetivo

Aplicar Suite Ultra UI v1 al diálogo compartido de confirmación usado por el módulo Tickets.

Este diálogo se utiliza en flujos sensibles como aceptar cierre, rechazar cierre y confirmaciones directas, por lo que el cambio debe ser visual y no debe alterar la respuesta booleana del modal.

### Alcance

- Aplicar paleta oficial Ultra.
- Mejorar título, mensaje y jerarquía visual.
- Mejorar botones de aceptar/cancelar.
- Mantener `true` al confirmar.
- Mantener `false` al cancelar.
- Mantener compatibilidad con `titulo`, `mensaje`, `textoAceptar` y `textoCancelar`.

### No alcance

- No cambiar lógica TypeScript.
- No cambiar payloads.
- No cambiar permisos.
- No cambiar backend.
- No reemplazar todavía el `prompt` de rechazo RRHH.

### Validación

Antes del commit debe comprobarse:

- El diálogo abre correctamente.
- Cancelar devuelve `false`.
- Aceptar devuelve `true`.
- Los textos personalizados siguen funcionando.
- Los flujos de aceptar/rechazar cierre siguen funcionando.