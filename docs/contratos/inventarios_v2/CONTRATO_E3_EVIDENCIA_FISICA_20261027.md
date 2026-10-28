# Inventarios V2 · E3 — Contrato operativo de evidencia para faltantes y hallazgos

**Corte:** 2026-10-27 · **PR:** #1134 DRAFT  
**Estado:** POLÍTICA RATIFICADA E IMPLEMENTADA EN PR DRAFT. CI del nuevo corte pendiente de comprobación; sin grants, merge ni despliegue.  
**Ámbito:** `NOT_LOCATED` → `AJUSTAR_A_CERO` y `UNREGISTERED_FIND` → `VINCULAR_EXISTENTE`. Las reglas generales de aprobación E3 y la matriz por tipo de activo se conservan.

## 1. Hallazgo de la auditoría del código

- E2 ya almacena `fecha_observacion_local` y `evidencia_descriptiva`, pero `_validate_payload()` acepta ambos ausentes. La UI E2 también permite enviarlos vacíos.
- E3 `_resolution_for()` exige justificación de 20 a 2,000 caracteres y acción explícita, pero **no exige fecha ni evidencia original documentada**. Un texto largo no verifica por sí mismo una inspección física.
- No hay en este flujo repositorio de fotografías, adjuntos con hash, segunda firma ni conciliación automática con tickets/movimientos; no debe afirmarse que se verifican automáticamente.
- Las decisiones guardan `actor_usuario_id`, `motivo_decision`, resolución, stock anterior/posterior y fecha; esto permite atribuir la decisión, **no** probar automáticamente que la revisión física ocurrió.

## 2. Regla transversal propuesta

Para **aprobar** uno de estos casos, y también para nuevas solicitudes E2 de esos dos tipos:

1. `fecha_observacion_local` obligatoria, fecha civil de sucursal válida, no futura. No usar fecha de carga como sustituto de fecha del conteo.
2. `evidencia_descriptiva` obligatoria (mínimo propuesto 20 caracteres significativos tras `strip()`; máximo actual 2,000). Describir dónde y cómo se revisó, no basta con «equipo no encontrado» o «sí existe». **Un límite de caracteres no valida veracidad**: el autorizador debe evaluar el contenido.
3. `motivo` de E2 y `motivo_decision` E3 permanecen distintos; `resoluciones[id].justificacion` sigue siendo una explicación específica (20–2,000 caracteres). No concatenar ni sustituir una evidencia por una justificación.
4. La descripción y la fecha se leen de la solicitud **persistida en DB** bajo el lock de E3. Faltar cualquiera → **422 `evidence_required`** sin cambio de stock, sin decisiones parciales y sin conversión automática de PENDING. Rechazar sí será posible con su motivo, incluso si faltó evidencia.
5. La UI E2 deberá señalar fecha y evidencia obligatorias para esos dos tipos; E3 mostrará ambas junto al baseline. **La validación crítica vive en el servicio Flask**, nunca únicamente en Angular.
6. PENDINGS previos sin estos campos **no podrán aprobarse sin corrección documental trazable**. No rellenar campos automáticamente ni reescribir solicitudes históricas. En ausencia de endpoint de anexar evidencia auditada, rechazar con motivo y crear una nueva solicitud E2 con fecha/evidencia, conservando trazabilidad. Nunca modificar #1/#2 de ULTRA DEMO como prueba.

## 3. NOT_LOCATED — ausencia TOTAL de una referencia

**Condición de uso:** existe referencia oficial en `inventario_general`, asignación a la sucursal y **stock oficial positivo**; tras el conteo se verifican **cero unidades físicas** de *esa misma referencia* en esa sucursal. `AJUSTAR_A_CERO` significa bajar **todas** las unidades del stock esperado a cero, no «descontar un equipo» ni «marcarlo inactivo».

**Evidencia física mínima que debe describir E2:**
- Ubicación/áreas concretas revisadas y fecha de la observación.
- Código interno/etiqueta de la referencia si existe, tipo aparatos/dispositivos y cantidad oficial contra la que se contó.
- Constancia descriptiva de que **se buscaron todas las unidades de la referencia** y no se encontró ninguna; revisar posibles movimientos, traslado, mantenimiento, préstamo o ubicación alterna antes de catalogarla como faltante.

**Responsable E3:** ADMICORP o Mantenimiento/Coordinación para aparatos, Sistemas para dispositivos, siempre con grant y sucursal asignada. Debe revisar evidencia, identidad, estado actual del stock y registrar justificación explícita por solicitud. Sin explicación suficiente, rechazar o mantener PENDING.

**Invariantes técnicas:**
- `stock_esperado > 0`, `stock_oficial_actual == stock_esperado == baseline`, referencia/tipo/sucursal válidos, `AJUSTAR_A_CERO` explícito, motivo. Mismo commit: `stock_nuevo=0`, delta negativo, auditoría.
- Si existe **alguna unidad física**, se usa `QUANTITY_DIFFERENCE` con `cantidad_fisica` real; no `NOT_LOCATED`. Si hay unidades en otra ubicación, investigar movimiento/transferencia, no simular baja de todo el stock.
- Si el stock cambió tras la observación, devolver **409** y levantar nueva solicitud (no copiar baseline ni adaptar `stock_esperado` silenciosamente).

**Ejemplo:** sistema registra 3 caminadoras de la misma referencia. Una está presente y faltan dos → `QUANTITY_DIFFERENCE` de 3 a 1, **NO** `AJUSTAR_A_CERO`. Si faltan las tres tras búsqueda trazable, puede solicitarse `NOT_LOCATED` con stock esperado 3 y ajuste a cero autorizado.

### Protección contra elusión del ajuste a cero (implementada en PR DRAFT)

La operación `QUANTITY_DIFFERENCE` **exige `cantidad_fisica > 0`**: una diferencia que pretenda establecer cantidad cero se rechaza en E2 (HTTP 400) y también en aprobación E3 de una solicitud histórica (HTTP 422 `zero_requires_not_located`). El camino legítimo es `NOT_LOCATED`, con fecha, evidencia y `AJUSTAR_A_CERO` explícito.

`NOT_LOCATED` se acepta en E2 únicamente con **stock oficial positivo**; no se crea un pendiente imposible de conciliar para una referencia ya en cero. El frontend refleja ambos límites; Flask es la fuente autoritativa. Rechazar un registro histórico inválido sigue permitido y no modifica existencias.

## 4. UNREGISTERED_FIND — hallazgo FÍSICO con registro oficial EXISTENTE

**Condición de uso:** se observó una unidad o conjunto de unidades físicas **no contabilizadas** en existencias de la sucursal, pero sí pertenecientes a una **referencia maestra canónica existente**, con fila de stock ya asignada a la misma sucursal. No genera ficha de aparato/dispositivo nueva; `CREAR_NUEVO` permanece 422.

**Evidencia física mínima que debe describir E2:**
- Fecha, ubicación y cantidad físicamente encontrada.
- Identificador real leído del equipo (`codigo_interno`/etiqueta cuando existe), tipo `aparatos` o `dispositivos`, nombre/marca si aportan identificación.
- Explicación de por qué las unidades halladas no están incluidas en el stock existente, evitando doble conteo, traspasos pendientes o otra solicitud de corrección.

**Responsable E3:** verifica sucursal, clase del activo, código físico exacto cuando el maestro tiene código, stock destino bajo lock y **cantidad física final TOTAL**. Este número final debe ser entero **mayor** al stock oficial previo; no interpretarlo como «unidades nuevas para sumar» (el código actual usa `stock_nuevo=cantidad_fisica`).

**Invariantes técnicas:**
- `VINCULAR_EXISTENTE` explícito, `inventario_id` destino realmente presente en `inventario_sucursal` de la sucursal, clase compatible con rol/observación, identidad verificable.
- `stock_esperado == stock_actual`; `cantidad_fisica > stock_esperado` y no más de 100000 según contrato vigente. Auditar delta en un commit, no duplicar como entrada V1.
- Se exige código oficial y etiqueta física del hallazgo coincidentes. **Sin código verificable E3 deniega la vinculación, también a administración corporativa**. Estos casos requieren un procedimiento de identificación adicional distinto, aún no implementado; el nombre por sí solo no autoriza efectos.
- Si no existe referencia maestra adecuada o no está asignada a la sucursal, NO crearla ni vincular a otra clase: PENDING/rechazo con motivo y apertura posterior de flujo maestro gobernado.

**Ejemplo:** referencia oficial de router en la sucursal: stock 1. Conteo físico total comprueba 2 routers del mismo código. La resolución es `stock_esperado=1`, `cantidad_fisica=2` (efecto +1), **NO** cantidad física 1 para que el backend sume uno.

## 5. Decisión humana y evidencia

- **E2: quien observa** registra fecha, descripción y motivo; su identidad autenticada y `creado_en_utc` quedan en DB.
- **E3: quien autoriza** debe ser distinto del creador, confirmar clase/competencia y sucursal, evaluar la evidencia y escribir una justificación de resolución y motivo de la decisión. La confirmación genérica de Angular no sustituye la autorización real del backend.
- **Faltan verificaciones materiales que no deben fingirse:** actualmente el servicio no consulta movimientos/tickets/PM para confirmar ausencias ni guarda fotos; la captura libre y la revisión humana son evidencia declarativa. Si se desea prueba documental fuerte, E4 debe integrar adjuntos/hash/ubicaciones e inspección trazable, con política de retención.
- **Cualquier incertidumbre** de identidad, stock o procedencia debe impedir una aprobación automática. Se puede rechazar con fundamento, sin tocar el inventario oficial.

## 6. Implementación realizada en PR DRAFT — pendiente de validación final

Archivos y puntos, en el orden indicado:
1. `backend/app/services/inventario_correccion_decisiones_service.py::decidir_lote`: antes de crear lote y **tras autorización E3**, en `APPROVED` para esos dos tipos, exigir fecha/evidencia de la solicitud real; error 422 uniforme, rollback. Los datos siguen inmutables en E2; REJECTED permitido.
2. `backend/app/routes/inventario_solicitudes_routes.py::_validate_payload`: para nuevas solicitudes E2 especiales, exigir esos campos, sin reescribir históricos y conservando la idempotencia.
3. `frontend/src/app/inventario/solicitudes/solicitudes-correccion.component.ts::puedeEnviar`: reflejar requisitos, HTML solo bindings/mensajes; sin controles simulados ni permisos Angular.
4. `frontend/src/app/inventario/revision-correcciones/revision-correcciones.component.ts::puedeConfirmar`: mostrar bloqueo por evidencia incompleta antes de confirmar, sin sustituir guard Flask; el detalle E3 mostrará fecha.
5. QA con PostgreSQL temporal: E2 sin fecha/evidencia 400; E3 sobre un PENDING histórico incompleto 422 sin efecto; aprobación completa de ambos casos 201, idempotencia 200; rechazo de uno incompleto 201 sin efecto; lote mixto con uno incompleto rollback total; autoaprobación/IDOR no filtrados por mensaje de evidencia.

La ratificación operativa fue confirmada. Validación Flask y Angular, más QA sintético, incorporados en PR #1134. Los resultados CI sobre el HEAD final, la auditoría independiente y el rollout siguen pendientes.

## 7. Criterios ratificados

**Reglas aprobadas:**
- Fecha local obligatoria + evidencia descriptiva ≥20 caracteres para nuevas solicitudes y aprobaciones especiales.
- Ajuste a cero solo por ausencia **total**, tras verificar ubicaciones y posibles movimientos.
- Vincular solo a referencia oficial preexistente con identidad física, sin alta automática ni doble conteo; cantidad informada es el total final.
- Casos sin código/identidad única no se aprueban en E3: revisión e identificación por procedimiento independiente pendiente, sin bypass corporativo.
- Foto/documento adjunto recomendable como evolución E4; no obligatorio ni falsamente «verificado» por E3 actual.

**Estado gate:** política ratificada, implementación en PR DRAFT. CI, revisión independiente, QA autenticado no destructivo y autorización explícita de despliegue continúan abiertos.
